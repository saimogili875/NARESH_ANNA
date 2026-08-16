import logging
import requests
from django.conf import settings

logger = logging.getLogger('whatsapp_sender')

LANGUAGE_NAMES = {
    'hi': 'Hindi',
    'te': 'Telugu',
    'en': 'English',
}

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


def translate_text(text: str, target_language: str) -> str:
    """
    Translates input text to target_language ('hi', 'te', 'en') using Gemini API.
    If target_language is 'en' or text is empty or GEMINI_API_KEY is not set, returns original text.
    """
    if not text or not text.strip():
        return text

    target_lang_code = (target_language or 'en').lower().strip()
    if target_lang_code not in LANGUAGE_NAMES or target_lang_code == 'en':
        return text

    api_key = getattr(settings, 'GEMINI_API_KEY', '').strip()
    if not api_key:
        logger.info(f"GEMINI_API_KEY not set. Returning original text for language {target_lang_code}.")
        return text

    target_lang_name = LANGUAGE_NAMES[target_lang_code]
    prompt = (
        f"Translate the following educational/school notification text accurately and naturally into {target_lang_name} ({target_lang_code} script). "
        f"Do not add any preamble, explanations, markdown formatting, or extra text. Return ONLY the translated string.\n\n"
        f"Text to translate:\n{text}"
    )

    url = f"{GEMINI_API_URL}?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 500,
        }
    }

    try:
        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    translated = parts[0].get("text", "").strip()
                    if translated:
                        logger.info(f"Successfully translated text to {target_lang_name} via Gemini.")
                        return translated
        logger.warning(f"Gemini API response status {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Gemini API translation error: {e}")

    return text


def translate_template_params(params: list, target_language: str) -> list:
    """
    Translates a list of string parameters for WhatsApp templates into the target language.
    Numbers, dates, and simple codes are preserved.
    """
    target_lang_code = (target_language or 'en').lower().strip()
    if target_lang_code not in LANGUAGE_NAMES or target_lang_code == 'en':
        return params

    translated_params = []
    for param in params:
        param_str = str(param)
        # Skip translating pure numbers or date patterns like 15-08-2026
        if param_str.replace('.', '').replace('-', '').replace('/', '').isdigit():
            translated_params.append(param_str)
        else:
            translated_params.append(translate_text(param_str, target_lang_code))

    return translated_params
