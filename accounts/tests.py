from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User, LoginLog
from captcha.models import CaptchaStore

class LoginAuditLogsTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_audit', password='Password123!', role='admin', is_staff=True, is_superuser=True
        )
        self.client = Client()

    def test_successful_login_creates_login_log(self):
        hashkey = CaptchaStore.generate_key()
        captcha_response = CaptchaStore.objects.get(hashkey=hashkey).challenge
        res = self.client.post(reverse('login'), {
            'username': 'admin_audit',
            'password': 'Password123!',
            'human_typed': 'true',
            'captcha_0': hashkey,
            'captcha_1': captcha_response,
        })
        self.assertEqual(res.status_code, 302)
        log = LoginLog.objects.filter(username='admin_audit', status='SUCCESS').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'SUCCESS')

    def test_failed_login_creates_login_log(self):
        hashkey = CaptchaStore.generate_key()
        captcha_response = CaptchaStore.objects.get(hashkey=hashkey).challenge
        res = self.client.post(reverse('login'), {
            'username': 'admin_audit',
            'password': 'WrongPassword!',
            'human_typed': 'true',
            'captcha_0': hashkey,
            'captcha_1': captcha_response,
        })
        self.assertEqual(res.status_code, 200)
        log = LoginLog.objects.filter(username='admin_audit', status='FAILED').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.failure_reason, 'Invalid password')

    def test_login_logs_view_accessible_by_admin(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse('login_logs'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Login Audit Logs')

    def test_group_list_view_renders_successfully(self):
        self.client.force_login(self.admin)
        res = self.client.get(reverse('group_list'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Academic Structure')

