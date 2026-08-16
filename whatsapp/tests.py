from unittest.mock import patch
from django.test import TestCase
from whatsapp.models import PendingMessage
from whatsapp.gemini_service import translate_text, translate_template_params
from whatsapp.services import send_absence_alert, build_template_components
from django.core.management import call_command


class WhatsAppMultilingualTestCase(TestCase):
    def test_gemini_translation_fallback(self):
        # Without GEMINI_API_KEY set, translate_text should safely return original text
        original = "Student is absent"
        translated = translate_text(original, "te")
        self.assertEqual(translated, original)

    def test_build_template_components(self):
        params = ["John Doe", "16-08-2026", "Absent"]
        components = build_template_components(params)
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0]["type"], "body")
        self.assertEqual(len(components[0]["parameters"]), 3)
        self.assertEqual(components[0]["parameters"][0]["text"], "John Doe")

    @patch('whatsapp.services.requests.post')
    def test_send_absence_alert_template(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "messages": [{"id": "wamid.HBgL"}]
        }

        res = send_absence_alert(
            student_name="Rahul",
            parent_phone="9876543210",
            date_str="16-08-2026",
            section="MPC-1A",
            reason="Unwell",
            language="te"
        )
        self.assertTrue(res["success"])
        self.assertTrue(mock_post.called)
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["type"], "template")
        self.assertEqual(payload["template"]["language"]["code"], "te")

    @patch('whatsapp.services.requests.post')
    def test_send_pending_whatsapp_command_template(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "messages": [{"id": "wamid.HBgL123"}]
        }

        msg = PendingMessage.objects.create(
            phone="9876543210",
            message_type=PendingMessage.TYPE_TEMPLATE,
            template_name="absence_alert",
            template_params=["Student Name", "16-08-2026", "Health Issue"],
            language="hi",
            message="Fallback message text",
            status=PendingMessage.STATUS_PENDING
        )

        call_command('send_pending_whatsapp', '--batch-size=10')

        msg.refresh_from_db()
        self.assertEqual(msg.status, PendingMessage.STATUS_SENT)
        self.assertTrue(mock_post.called)
