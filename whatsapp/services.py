import logging
import requests
from django.conf import settings

from .gemini_service import translate_text, translate_template_params

logger = logging.getLogger('whatsapp_sender')

META_API_URL = "https://graph.facebook.com/v21.0"


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
    # Replace newlines with spaces as required by Meta Cloud API template parameter rules
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


def send_whatsapp_template(to_number: str, template_name: str, language: str = "en", components: list = None) -> dict:
    phone = _normalize_phone(to_number)
    phone_id = settings.META_WHATSAPP_PHONE_ID
    url = f"{META_API_URL}/{phone_id}/messages"

    # Meta API expects standard language code (e.g. 'en') when sending trilingual parameters
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

    try:
        resp = requests.post(url, json=payload, headers=_get_headers(), timeout=30)
        data = resp.json()
        if resp.status_code in (200, 201):
            msg_id = data.get("messages", [{}])[0].get("id", "")
            logger.info(f"Template '{template_name}' ({meta_lang_code}) sent to {phone}: {msg_id}")
            return {"success": True, "message_id": msg_id, "to": phone}
        else:
            error = data.get("error", {}).get("message", resp.text)
            logger.error(f"Template '{template_name}' send failed to {phone}: {error}")
            return {"success": False, "error": error}
    except Exception as e:
        logger.error(f"Template send exception to {phone}: {e}")
        return {"success": False, "error": str(e)}


def send_whatsapp_text(to_number: str, message: str) -> dict:
    phone = _normalize_phone(to_number)
    phone_id = settings.META_WHATSAPP_PHONE_ID
    url = f"{META_API_URL}/{phone_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message},
    }

    try:
        resp = requests.post(url, json=payload, headers=_get_headers(), timeout=30)
        data = resp.json()
        if resp.status_code in (200, 201):
            msg_id = data.get("messages", [{}])[0].get("id", "")
            logger.info(f"Text sent to {phone}: {msg_id}")
            return {"success": True, "message_id": msg_id, "to": phone}
        else:
            error = data.get("error", {}).get("message", resp.text)
            logger.error(f"Text send failed to {phone}: {error}")
            return {"success": False, "error": error}
    except Exception as e:
        logger.error(f"Text send exception to {phone}: {e}")
        return {"success": False, "error": str(e)}


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

    try:
        resp = requests.post(url, json=payload, headers=_get_headers(), timeout=30)
        data = resp.json()
        if resp.status_code in (200, 201):
            msg_id = data.get("messages", [{}])[0].get("id", "")
            logger.info(f"Media sent to {phone}: {msg_id}")
            return {"success": True, "message_id": msg_id, "to": phone}
        else:
            error = data.get("error", {}).get("message", resp.text)
            logger.error(f"Media send failed to {phone}: {error}")
            return {"success": False, "error": error}
    except Exception as e:
        logger.error(f"Media send exception to {phone}: {e}")
        return {"success": False, "error": str(e)}


def send_exam_marks(parent_phone: str, student_name: str, marks: str, total_marks: str, subject: str, date_str: str, language: str = "en") -> dict:
    template_name = settings.META_TEMPLATE_EXAM_MARKS
    components = build_template_components([
        student_name,
        str(marks),
        str(total_marks),
        subject,
        date_str,
    ])
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
    from django.db import close_old_connections
    close_old_connections()
    from whatsapp.models import PendingMessage

    try:
        pending = list(
            PendingMessage.objects.filter(
                status=PendingMessage.STATUS_PENDING
            ).order_by('created_at')[:batch_size]
        )
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
            gen_template = getattr(settings, 'META_TEMPLATE_GENERAL', 'general_notification')
            if not result["success"] and template_name != gen_template:
                gen_components = build_template_components([msg.message])
                result = send_whatsapp_template(
                    to_number=phone,
                    template_name=gen_template,
                    language=language,
                    components=gen_components
                )
        else:
            result = send_whatsapp_text(to_number=phone, message=msg.message)

        if result["success"]:
            msg.status = PendingMessage.STATUS_SENT
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

