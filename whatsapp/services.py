import json

from twilio.rest import Client
from django.conf import settings


def _normalize_whatsapp_number(to_number: str) -> str:
    """
    Ensure the number is in 'whatsapp:+<countrycode><number>' format,
    regardless of how it was passed in.

    Handles:
      - "+919876543210"        -> "whatsapp:+919876543210"
      - "919876543210"         -> "whatsapp:+919876543210"
      - "9876543210" (10 digit)-> "whatsapp:+919876543210" (assumes India)
      - "whatsapp:+919876543210" -> "whatsapp:+919876543210"
    """
    to_number = to_number.strip()

    if to_number.startswith("whatsapp:"):
        to_number = to_number[len("whatsapp:"):]

    # Remove spaces, dashes etc.
    to_number = "".join(ch for ch in to_number if ch.isdigit() or ch == "+")

    if to_number.startswith("+"):
        pass  # already has country code
    elif len(to_number) == 10:
        # Bare 10-digit number, assume India
        to_number = f"+91{to_number}"
    elif to_number.startswith("91") and len(to_number) == 12:
        to_number = f"+{to_number}"
    else:
        to_number = f"+{to_number}"

    return f"whatsapp:{to_number}"


def send_whatsapp_message(to_number: str, message: str) -> dict:
    """
    Send a WhatsApp message via Twilio.

    Args:
        to_number: Recipient's phone number with country code e.g. +919876543210
        message: Text message to send

    Returns:
        dict with status and message SID or error
    """
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        msg = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_FROM,
            body=message,
            to=_normalize_whatsapp_number(to_number),
        )

        return {
            "success": True,
            "sid": msg.sid,
            "status": msg.status,
            "to": to_number,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def send_whatsapp_media(to_number: str, media_url: str, caption: str = "") -> dict:
    """
    Send a media file (e.g. PDF, image) via WhatsApp using Twilio.

    Args:
        to_number: Recipient's phone number with country code e.g. +919876543210
        media_url: Publicly accessible HTTPS URL to the file (Twilio fetches it)
        caption: Optional text to accompany the media

    Returns:
        dict with status and message SID or error
    """
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        msg = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=_normalize_whatsapp_number(to_number),
            body=caption,
            media_url=[media_url],
        )

        return {
            "success": True,
            "sid": msg.sid,
            "status": msg.status,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def send_whatsapp_template(to_number: str, template_sid: str, variables: dict = None) -> dict:
    """
    Send a pre-approved WhatsApp template message.

    Args:
        to_number: Recipient's phone number e.g. +919876543210
        template_sid: Twilio Content Template SID (HXxxxx)
        variables: Template variable substitutions e.g. {"1": "John", "2": "Order#123"}

    Returns:
        dict with status and message SID or error
    """
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        msg = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=_normalize_whatsapp_number(to_number),
            content_sid=template_sid,
            content_variables=json.dumps(variables or {}),
        )

        return {
            "success": True,
            "sid": msg.sid,
            "status": msg.status,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
