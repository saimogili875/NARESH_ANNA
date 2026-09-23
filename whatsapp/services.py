import logging
import threading
import time
import requests
from django.conf import settings

from .gemini_service import translate_text, translate_template_params

logger = logging.getLogger('whatsapp_sender')

META_API_URL = "https://graph.facebook.com/v21.0"

# Global in-process rate limiter lock & last sent timestamp.
# Intentionally throttles requests to max 1 message every 6 seconds to:
# (a) Stay safely under Meta Cloud API rate limits.
# (b) Smooth out traffic bursts when multiple faculty members save attendance near peak cutoff hours.
WHATSAPP_MIN_INTERVAL_SECONDS = 6.0

_rate_limit_lock = threading.Lock()
_last_sent_at = 0.0


def _apply_rate_limit():
    global _last_sent_at
    min_interval = getattr(settings, 'WHATSAPP_MIN_INTERVAL_SECONDS', 6.0)
    with _rate_limit_lock:
        now = time.monotonic()
        elapsed = now - _last_sent_at
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_sent_at = time.monotonic()


def _get_headers():
    return {
        "Authorization": f"Bearer {settings.META_WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }


def _normalize_phone(phone: str) -> str:
    phone = phone.strip()
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        digits = f"91{digits}"
    elif digits.startswith("91") and len(digits) == 12:
        pass
    elif digits.startswith("+"):
        digits = digits[1:]
    return digits


def _sanitize_param(val) -> str:
    if val is None:
        return "-"
    s = str(val).strip()
    if not s:
        return "-"
    s = s.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return s[:1000]


def build_template_components(params: list) -> list:
    """
    Constructs Meta WhatsApp Graph API components list from a list of parameter strings/values.
    Sanitizes each parameter to ensure no raw newlines or empty values break Meta Cloud API rules.
    """
    if not params:
        return []
    if isinstance(params, list) and len(params) > 0 and isinstance(params[0], dict) and "type" in params[0]:
        return params

    text_params = [{"type": "text", "text": _sanitize_param(p)} for p in params]
    return [
        {
            "type": "body",
            "parameters": text_params,
        }
    ]


import random

def _post_with_retry(url, json_payload=None, headers=None, timeout=30, max_retries=3):
    """
    POST request wrapper with exponential backoff and jitter for transient errors.
    Does NOT retry permanent client errors (400, 401, 403, 404).
    """
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(url, json=json_payload, headers=headers, timeout=timeout)
            if resp.status_code in (200, 201):
                return resp
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                backoff = (2 ** attempt) + random.uniform(0.1, 0.5)
                logger.warning(f"Transient HTTP {resp.status_code} for {url}. Retrying in {backoff:.2f}s (attempt {attempt+1}/{max_retries})...")
                time.sleep(backoff)
                continue
            return resp
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            if attempt < max_retries:
                backoff = (2 ** attempt) + random.uniform(0.1, 0.5)
                logger.warning(f"Request exception {exc} for {url}. Retrying in {backoff:.2f}s (attempt {attempt+1}/{max_retries})...")
                time.sleep(backoff)
                continue
            raise exc


def send_whatsapp_template(to_number: str, template_name: str, language: str = "en", components: list = None) -> dict:
    phone = _normalize_phone(to_number)
    phone_id = getattr(settings, 'META_WHATSAPP_PHONE_ID', '').strip()
    token = getattr(settings, 'META_WHATSAPP_TOKEN', '').strip()

    if not phone_id or not token:
        error_msg = "META_WHATSAPP_PHONE_ID or META_WHATSAPP_TOKEN is missing in environment variables."
        logger.error(f"Template '{template_name}' send failed to {phone}: {error_msg}")
        return {"success": False, "error": error_msg, "status_code": 401}

    url = f"{META_API_URL}/{phone_id}/messages"
    meta_lang_code = "en" if (language or "").lower() in ('all', 'trilingual', 'multi') else (language or "en")

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": meta_lang_code},
        },
    }
    if components:
        payload["template"]["components"] = components

    param_count = 0
    if components:
        for comp in components:
            param_count += len(comp.get("parameters", []))
    logger.info(f"Sending template '{template_name}' to {phone} with {param_count} params, lang={meta_lang_code}")

    _apply_rate_limit()
    try:
        resp = _post_with_retry(url, json_payload=payload, headers=_get_headers(), timeout=30)
        data = resp.json()
        if resp.status_code in (200, 201):
            msg_id = data.get("messages", [{}])[0].get("id", "")
            logger.info(f"Template '{template_name}' ({meta_lang_code}) sent to {phone}: {msg_id}")
            return {"success": True, "message_id": msg_id, "wamid": msg_id, "to": phone, "status_code": 200}
        else:
            error = data.get("error", {}).get("message", resp.text)
            logger.error(f"Template '{template_name}' send failed to {phone}: {error}")
            return {"success": False, "error": error, "status_code": resp.status_code}
    except Exception as e:
        logger.error(f"Template send exception to {phone}: {e}")
        return {"success": False, "error": str(e), "status_code": 504 if "timeout" in str(e).lower() else 500}


def send_whatsapp_text(to_number: str, message: str) -> dict:
    phone = _normalize_phone(to_number)
    phone_id = getattr(settings, 'META_WHATSAPP_PHONE_ID', '').strip()
    token = getattr(settings, 'META_WHATSAPP_TOKEN', '').strip()

    if not phone_id or not token:
        error_msg = "META_WHATSAPP_PHONE_ID or META_WHATSAPP_TOKEN is missing in environment variables."
        logger.error(f"Text send failed to {phone}: {error_msg}")
        return {"success": False, "error": error_msg, "status_code": 401}

    url = f"{META_API_URL}/{phone_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message},
    }

    _apply_rate_limit()
    try:
        resp = _post_with_retry(url, json_payload=payload, headers=_get_headers(), timeout=30)
        data = resp.json()
        if resp.status_code in (200, 201):
            msg_id = data.get("messages", [{}])[0].get("id", "")
            logger.info(f"Text sent to {phone}: {msg_id}")
            return {"success": True, "message_id": msg_id, "wamid": msg_id, "to": phone, "status_code": 200}
        else:
            error = data.get("error", {}).get("message", resp.text)
            logger.error(f"Text send failed to {phone}: {error}")
            return {"success": False, "error": error, "status_code": resp.status_code}
    except Exception as e:
        logger.error(f"Text send exception to {phone}: {e}")
        return {"success": False, "error": str(e), "status_code": 504 if "timeout" in str(e).lower() else 500}


def send_absence_alert(student_name: str, parent_phone: str, date_str: str, section: str, reason: str = "", language: str = "en") -> dict:
    template_name = settings.META_TEMPLATE_ABSENCE
    reason_text = reason or "Not provided"

    components = build_template_components([
        student_name,
        date_str,
        reason_text,
    ])
    return send_whatsapp_template(parent_phone, template_name, language="en", components=components)


def send_faculty_absence_alert(faculty_name: str, phone: str, date_str: str, language: str = "en") -> dict:
    template_name = settings.META_TEMPLATE_FACULTY_ABSENCE
    components = build_template_components([
        faculty_name,
        date_str,
    ])
    return send_whatsapp_template(phone, template_name, language="en", components=components)


def send_whatsapp_media(to_number: str, media_url: str, caption: str = "") -> dict:
    phone = _normalize_phone(to_number)
    phone_id = settings.META_WHATSAPP_PHONE_ID
    url = f"{META_API_URL}/{phone_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "document",
        "document": {
            "link": media_url,
            "caption": caption,
        },
    }

    _apply_rate_limit()
    try:
        resp = requests.post(url, json=payload, headers=_get_headers(), timeout=30)
        data = resp.json()
        if resp.status_code in (200, 201):
            msg_id = data.get("messages", [{}])[0].get("id", "")
            logger.info(f"Media sent to {phone}: {msg_id}")
            return {"success": True, "message_id": msg_id, "wamid": msg_id, "to": phone}
        else:
            error = data.get("error", {}).get("message", resp.text)
            logger.error(f"Media send failed to {phone}: {error}")
            return {"success": False, "error": error}
    except Exception as e:
        logger.error(f"Media send exception to {phone}: {e}")
        return {"success": False, "error": str(e)}


def send_exam_marks(parent_phone: str, student_name: str, marks: str, total_marks: str, subject: str, date_str: str, subject_marks: str = "", language: str = "en") -> dict:
    template_name = settings.META_TEMPLATE_EXAM_MARKS
    params = [student_name, str(marks), str(total_marks), subject, date_str]
    if subject_marks:
        params.append(subject_marks)
    components = build_template_components(params)
    return send_whatsapp_template(parent_phone, template_name, language="en", components=components)


def send_generic_template(to_number: str, message: str, template_name: str = None, language: str = "en") -> dict:
    """
    Sends generic message using Meta WhatsApp Template payload in English.
    """
    template = template_name or getattr(settings, 'META_TEMPLATE_GENERAL', 'general_notification')
    components = build_template_components([message])
    return send_whatsapp_template(to_number, template, language="en", components=components)


def dispatch_pending_messages(batch_size: int = 50) -> dict:
    """
    Dispatches pending messages in DB via Meta Cloud API templates/text.
    """
    from whatsapp.models import PendingMessage
    from django.db import transaction
    from django.utils import timezone
    from datetime import timedelta
    try:
        # Reclaim stale processing messages older than 10 minutes (e.g. from crashed workers)
        stale_threshold = timezone.now() - timedelta(minutes=10)
        PendingMessage.objects.filter(
            status=PendingMessage.STATUS_PROCESSING,
            updated_at__lt=stale_threshold
        ).update(status=PendingMessage.STATUS_PENDING)

        with transaction.atomic():
            pending_ids = list(
                PendingMessage.objects.select_for_update(skip_locked=True)
                .filter(status=PendingMessage.STATUS_PENDING)
                .order_by('created_at')
                .values_list('id', flat=True)[:batch_size]
            )
            if not pending_ids:
                return {"sent": 0, "failed": 0}
            PendingMessage.objects.filter(id__in=pending_ids).update(status=PendingMessage.STATUS_PROCESSING)

        pending = list(PendingMessage.objects.filter(id__in=pending_ids).order_by('created_at'))
    except Exception as err:
        logger.error(f"Error querying pending messages: {err}")
        return {"sent": 0, "failed": 0}
    if not pending:
        return {"sent": 0, "failed": 0}

    sent = 0
    failed = 0
    for msg in pending:
        phone = (msg.phone or "").strip()
        if not phone:
            msg.status = PendingMessage.STATUS_FAILED
            msg.error_message = "No phone number"
            msg.save()
            failed += 1
            continue

        if getattr(msg, 'message_type', 'template') == PendingMessage.TYPE_TEMPLATE:
            template_name = msg.template_name or getattr(settings, 'META_TEMPLATE_GENERAL', 'general_notification')
            params = msg.template_params or [msg.message]
            components = build_template_components(params)
            language = msg.language or getattr(settings, 'WHATSAPP_DEFAULT_LANGUAGE', 'en')
            result = send_whatsapp_template(
                to_number=phone,
                template_name=template_name,
                language=language,
                components=components
            )
            if not result["success"]:
                logger.error(f"PendingMessage {msg.pk} template '{template_name}' failed: {result.get('error')}")
        else:
            result = send_whatsapp_text(to_number=phone, message=msg.message)

        if result["success"]:
            msg.status = PendingMessage.STATUS_SENT
            msg.wamid = result.get("wamid") or result.get("message_id") or ""
            msg.error_message = ""
            msg.save()
            sent += 1
        else:
            msg.status = PendingMessage.STATUS_FAILED
            msg.error_message = result.get("error", "Unknown error")
            msg.save()
            failed += 1

    return {"sent": sent, "failed": failed}


def dispatch_pending_messages_async(batch_size: int = 50):
    import threading
    thread = threading.Thread(target=dispatch_pending_messages, args=(batch_size,))
    thread.daemon = True
    thread.start()

