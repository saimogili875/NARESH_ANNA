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


def build_template_components(params: list) -> list:
    """
    Constructs Meta WhatsApp Graph API components list from a list of parameter strings/values.
    If params is already a list of dicts (e.g. [{"type": "body", ...}]), returns it directly.
    """
    if not params:
        return []
    if isinstance(params, list) and len(params) > 0 and isinstance(params[0], dict) and "type" in params[0]:
        return params

    text_params = [{"type": "text", "text": str(p)} for p in params]
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

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
        },
    }
    if components:
        payload["template"]["components"] = components

    try:
        resp = requests.post(url, json=payload, headers=_get_headers(), timeout=30)
        data = resp.json()
        if resp.status_code in (200, 201):
            msg_id = data.get("messages", [{}])[0].get("id", "")
            logger.info(f"Template '{template_name}' ({language}) sent to {phone}: {msg_id}")
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
    raw_reason = reason or "Not provided"
    
    # Translate reason using Gemini AI if language is hindi/telugu
    translated_reason = translate_text(raw_reason, language) if language in ('hi', 'te') else raw_reason

    components = build_template_components([
        student_name,
        date_str,
        translated_reason,
    ])
    return send_whatsapp_template(parent_phone, template_name, language=language, components=components)


def send_faculty_absence_alert(faculty_name: str, phone: str, date_str: str, language: str = "en") -> dict:
    template_name = settings.META_TEMPLATE_FACULTY_ABSENCE
    components = build_template_components([
        faculty_name,
        date_str,
    ])
    return send_whatsapp_template(phone, template_name, language=language, components=components)


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
    translated_subject = translate_text(subject, language) if language in ('hi', 'te') else subject
    
    components = build_template_components([
        student_name,
        str(marks),
        str(total_marks),
        translated_subject,
        date_str,
    ])
    return send_whatsapp_template(parent_phone, template_name, language=language, components=components)


def send_generic_template(to_number: str, message: str, template_name: str = None, language: str = "en") -> dict:
    """
    Sends generic message using Meta WhatsApp Template payload.
    Translates message using Gemini AI if language is hindi/telugu.
    """
    template = template_name or getattr(settings, 'META_TEMPLATE_GENERAL', 'general_notification')
    translated_message = translate_text(message, language) if language in ('hi', 'te') else message
    components = build_template_components([translated_message])
    return send_whatsapp_template(to_number, template, language=language, components=components)

