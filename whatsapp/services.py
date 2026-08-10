import logging
import requests
from django.conf import settings

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
            logger.info(f"Template sent to {phone}: {msg_id}")
            return {"success": True, "message_id": msg_id, "to": phone}
        else:
            error = data.get("error", {}).get("message", resp.text)
            logger.error(f"Template send failed to {phone}: {error}")
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


def send_absence_alert(student_name: str, parent_phone: str, date_str: str, section: str, reason: str = "") -> dict:
    template_name = settings.META_TEMPLATE_ABSENCE
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": student_name},
                {"type": "text", "text": date_str},
                {"type": "text", "text": section},
            ],
        }
    ]
    return send_whatsapp_template(parent_phone, template_name, components=components)


def send_exam_reminder(parent_phone: str, exam_name: str, exam_date: str, venue: str = "") -> dict:
    template_name = settings.META_TEMPLATE_EXAM_REMINDER
    components = [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": exam_name},
                {"type": "text", "text": exam_date},
                {"type": "text", "text": venue or "College campus"},
            ],
        }
    ]
    return send_whatsapp_template(parent_phone, template_name, components=components)
