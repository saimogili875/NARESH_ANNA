from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
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

    def test_get_state_changing_endpoints_rejected(self):
        res_retry = self.client.get(reverse('whatsapp-retry-failed'))
        self.assertEqual(res_retry.status_code, 405)

    def test_bug_012_message_status_list_authorization(self):
        anon_client = Client()
        res_anon = anon_client.get(reverse('whatsapp-status'))
        self.assertEqual(res_anon.status_code, 302)

        res_admin = self.client.get(reverse('whatsapp-status'))
        self.assertEqual(res_admin.status_code, 200)


class WhatsAppTriggerBatchTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.valid_token = '9f3a7c1e2b8d4f6a0c5e9b2d7a1f4c8e6b3d0a9f2c7e5b1d8a4f0c3e9b6d2a7f'
        cache.delete('whatsapp_trigger_batch_lock')

    def tearDown(self):
        cache.delete('whatsapp_trigger_batch_lock')

    def test_no_token_returns_403(self):
        with self.settings(WHATSAPP_TRIGGER_TOKEN=self.valid_token):
            response = self.client.get(reverse('whatsapp-trigger-batch'))
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.content, b'')

    def test_wrong_token_returns_403(self):
        with self.settings(WHATSAPP_TRIGGER_TOKEN=self.valid_token):
            url = f"{reverse('whatsapp-trigger-batch')}?token=invalid_token_xyz"
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.content, b'')

    def test_correct_token_processes_pending_messages(self):
        msg = PendingMessage.objects.create(
            phone='9876543210',
            message_type=PendingMessage.TYPE_TEMPLATE,
            template_name='general_notification',
            message='Test Batch Trigger',
            status=PendingMessage.STATUS_PENDING,
        )
        with self.settings(WHATSAPP_TRIGGER_TOKEN=self.valid_token):
            with patch('whatsapp.services.send_whatsapp_template', return_value={'success': True, 'wamid': 'wamid.test.123'}):
                url = f"{reverse('whatsapp-trigger-batch')}?token={self.valid_token}"
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertTrue(data['success'])
                self.assertEqual(data['sent'], 1)
                self.assertEqual(data['failed'], 0)

                msg.refresh_from_db()
                self.assertEqual(msg.status, PendingMessage.STATUS_SENT)
                self.assertEqual(msg.wamid, 'wamid.test.123')

    def test_batch_limit_is_25(self):
        for i in range(50):
            PendingMessage.objects.create(
                phone=f'98765432{i:02d}',
                message_type=PendingMessage.TYPE_TEXT,
                message=f'Batch message {i}',
                status=PendingMessage.STATUS_PENDING,
            )
        with self.settings(WHATSAPP_TRIGGER_TOKEN=self.valid_token):
            with patch('whatsapp.services.send_whatsapp_text', return_value={'success': True, 'wamid': 'wamid.25'}):
                url = f"{reverse('whatsapp-trigger-batch')}?token={self.valid_token}"
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertEqual(data['sent'], 25)
                self.assertEqual(PendingMessage.objects.filter(status=PendingMessage.STATUS_PENDING).count(), 25)

    def test_overlapping_run_does_not_double_send(self):
        PendingMessage.objects.create(
            phone='9876543210',
            message_type=PendingMessage.TYPE_TEXT,
            message='Overlap test',
            status=PendingMessage.STATUS_PENDING,
        )
        # Lock is active from another run
        cache.set('whatsapp_trigger_batch_lock', 'locked', timeout=300)

        with self.settings(WHATSAPP_TRIGGER_TOKEN=self.valid_token):
            with patch('whatsapp.services.send_whatsapp_text') as mock_send:
                url = f"{reverse('whatsapp-trigger-batch')}?token={self.valid_token}"
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertTrue(data['success'])
                self.assertEqual(data['sent'], 0)
                mock_send.assert_not_called()

    def test_stuck_processing_message_reset(self):
        stuck_msg = PendingMessage.objects.create(
            phone='9876543210',
            message_type=PendingMessage.TYPE_TEXT,
            message='Stuck message',
            status=PendingMessage.STATUS_PROCESSING,
        )
        # Set updated_at to 15 minutes in the past
        PendingMessage.objects.filter(pk=stuck_msg.pk).update(
            updated_at=timezone.now() - timedelta(minutes=15)
        )

        with self.settings(WHATSAPP_TRIGGER_TOKEN=self.valid_token):
            with patch('whatsapp.services.send_whatsapp_text', return_value={'success': True, 'wamid': 'wamid.stuck.fixed'}):
                url = f"{reverse('whatsapp-trigger-batch')}?token={self.valid_token}"
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                stuck_msg.refresh_from_db()
                self.assertEqual(stuck_msg.status, PendingMessage.STATUS_SENT)
