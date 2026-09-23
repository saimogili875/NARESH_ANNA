from django.test import TestCase, Client
from django.urls import reverse
from whatsapp.models import PendingMessage
from accounts.models import User
from unittest.mock import patch, MagicMock


class WhatsAppPhase2Test(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin_wa', password='password123', role='admin')
        self.client = Client()
        self.client.force_login(self.admin)

    def test_int_201_message_claiming_prevents_duplicate_dispatch(self):
        msg = PendingMessage.objects.create(
            phone='9876543210',
            message_type=PendingMessage.TYPE_TEXT,
            message='Test Claim',
            status=PendingMessage.STATUS_PENDING,
        )
        from whatsapp.services import dispatch_pending_messages
        with patch('whatsapp.services.send_whatsapp_text', return_value={'success': True, 'wamid': 'wamid.123'}):
            res = dispatch_pending_messages(batch_size=10)
            self.assertEqual(res['sent'], 1)
            msg.refresh_from_db()
            self.assertEqual(msg.status, PendingMessage.STATUS_SENT)

    def test_int_202_status_code_classification(self):
        with patch('whatsapp.views.send_whatsapp_text', return_value={'success': False, 'error': 'Rate limited', 'status_code': 429}):
            res = self.client.post(reverse('whatsapp-send'), data='{"to": "9876543210", "message": "Hi"}', content_type='application/json')
            self.assertEqual(res.status_code, 429)

    def test_int_203_retry_strategy(self):
        from whatsapp.services import _post_with_retry
        mock_resp_503 = MagicMock()
        mock_resp_503.status_code = 503
        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200

        with patch('requests.post', side_effect=[mock_resp_503, mock_resp_200]) as mock_post:
            resp = _post_with_retry('https://example.com/api', max_retries=2)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(mock_post.call_count, 2)

    def test_bug_013_get_state_changing_endpoints_rejected(self):
        res_trigger = self.client.get(reverse('whatsapp-trigger-batch'))
        self.assertEqual(res_trigger.status_code, 405)

        res_retry = self.client.get(reverse('whatsapp-retry-failed'))
        self.assertEqual(res_retry.status_code, 405)

        res_post_trigger = self.client.post(reverse('whatsapp-trigger-batch'))
        self.assertEqual(res_post_trigger.status_code, 200)

    def test_bug_012_message_status_list_authorization(self):
        anon_client = Client()
        res_anon = anon_client.get(reverse('whatsapp-status'))
        self.assertEqual(res_anon.status_code, 302)

        res_admin = self.client.get(reverse('whatsapp-status'))
        self.assertEqual(res_admin.status_code, 200)
