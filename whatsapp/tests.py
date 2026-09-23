from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core.management import call_command
from whatsapp.models import PendingMessage
from whatsapp.gemini_service import translate_text, translate_template_params
from whatsapp.services import send_absence_alert, build_template_components


@override_settings(META_WHATSAPP_PHONE_ID="123456789", META_WHATSAPP_TOKEN="test_token")
class WhatsAppMultilingualTestCase(TestCase):
    def test_gemini_translation_fallback(self):
        # Without GEMINI_API_KEY set, translate_text should safely return original text
        original = "Student is absent"
        translated = translate_text(original, "te")
        self.assertEqual(translated, original)

    def test_trilingual_translation_single_call(self):
        original = "Student is absent"
        translated = translate_text(original, "all")
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
        self.assertEqual(payload["template"]["language"]["code"], "en")

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
        self.assertEqual(msg.wamid, "wamid.HBgL123")
        self.assertTrue(mock_post.called)

    def test_message_status_list_view(self):
        from accounts.models import User
        user = User.objects.create_user(username="testuser", password="password")
        self.client.force_login(user)

        PendingMessage.objects.create(
            phone="9876543210",
            status=PendingMessage.STATUS_SENT,
            message="Test message"
        )

        response = self.client.get('/whatsapp/status/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "WhatsApp Status")
        self.assertContains(response, "9876543210")
        self.assertContains(response, "Sent")
        self.assertContains(response, "Showing last 20 messages")

    def test_message_status_list_search(self):
        from accounts.models import User
        from students.models import Student
        user = User.objects.create_user(username="searchuser", password="password")
        self.client.force_login(user)

        student = Student.objects.create(admission_number="ADM001", name="Raju Kumar", mobile="9988776655")
        PendingMessage.objects.create(
            student=student,
            phone="9988776655",
            status=PendingMessage.STATUS_SENT,
            message="Test message 1"
        )
        PendingMessage.objects.create(
            phone="1122334455",
            status=PendingMessage.STATUS_SENT,
            message="Test message 2"
        )

        response = self.client.get('/whatsapp/status/?q=Raju')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Raju Kumar")
        self.assertContains(response, "Showing 1 result(s) for 'Raju'")

        response_empty = self.client.get('/whatsapp/status/?q=NonExistent')
        self.assertEqual(response_empty.status_code, 200)
        self.assertContains(response_empty, "No messages found for 'NonExistent'")

    @override_settings(META_APP_SECRET="")
    def test_webhook_rejects_unsigned_payload_when_secret_unset(self):
        payload = {"entry": []}
        resp = self.client.post('/whatsapp/webhook/', data=payload, content_type='application/json')
        self.assertEqual(resp.status_code, 403)

    @override_settings(META_APP_SECRET="test_secret")
    def test_webhook_delivery_and_read_status_updates(self):
        import hmac, hashlib, json
        msg = PendingMessage.objects.create(
            phone="9876543210",
            status=PendingMessage.STATUS_SENT,
            wamid="wamid.TEST12345",
            message="Test tracking"
        )

        def post_signed(payload):
            body_bytes = json.dumps(payload).encode('utf-8')
            sig = 'sha256=' + hmac.new(b'test_secret', body_bytes, hashlib.sha256).hexdigest()
            return self.client.post(
                '/whatsapp/webhook/',
                data=body_bytes,
                content_type='application/json',
                HTTP_X_HUB_SIGNATURE_256=sig
            )

        # Test 'delivered' webhook payload
        payload_delivered = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{
                            "id": "wamid.TEST12345",
                            "status": "delivered"
                        }]
                    }
                }]
            }]
        }
        resp = post_signed(payload_delivered)
        self.assertEqual(resp.status_code, 200)
        msg.refresh_from_db()
        self.assertEqual(msg.status, PendingMessage.STATUS_DELIVERED)

        # Test 'read' webhook payload
        payload_read = {
            "entry": [{
                "changes": [{
                    "value": {
                        "statuses": [{
                            "id": "wamid.TEST12345",
                            "status": "read"
                        }]
                    }
                }]
            }]
        }
        resp = post_signed(payload_read)
        self.assertEqual(resp.status_code, 200)
        msg.refresh_from_db()
        self.assertEqual(msg.status, PendingMessage.STATUS_READ)


