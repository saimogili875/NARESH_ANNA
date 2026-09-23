from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User, Group, Section, AcademicYear, LoginLog
from students.models import Student
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


class GroupSectionSearchAndDeleteTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_group_test', password='Password123!', role='admin', is_staff=True, is_superuser=True
        )
        self.client = Client()
        self.client.force_login(self.admin)
        self.ay = AcademicYear.objects.create(
            name='2024-2025', is_active=True, start_date='2024-06-01', end_date='2025-05-31'
        )
        self.grp1 = Group.objects.create(name='MPC Group', code='MPC_TEST', academic_year=self.ay)
        self.grp2 = Group.objects.create(name='BiPC Group', code='BIPC_TEST', academic_year=self.ay)
        self.sec1 = Section.objects.create(group=self.grp1, year='1', name='A', academic_year=self.ay)
        self.sec2 = Section.objects.create(group=self.grp2, year='2', name='B', academic_year=self.ay)

    def test_group_search_exact_and_partial(self):
        res = self.client.get(reverse('group_list') + '?q=MPC_TEST')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'MPC Group')
        self.assertNotContains(res, 'BiPC Group')

    def test_group_search_case_insensitive_and_whitespace(self):
        res = self.client.get(reverse('group_list') + '?q=%20%20bipc_test%20%20')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'BiPC Group')
        self.assertNotContains(res, 'MPC Group')

    def test_group_search_empty_and_no_matches(self):
        res_empty = self.client.get(reverse('group_list') + '?q=')
        self.assertEqual(res_empty.status_code, 200)
        self.assertContains(res_empty, 'MPC Group')
        self.assertContains(res_empty, 'BiPC Group')

        res_none = self.client.get(reverse('group_list') + '?q=NON_EXISTENT_QUERY')
        self.assertEqual(res_none.status_code, 200)
        self.assertNotContains(res_none, 'MPC Group')

    def test_section_search(self):
        res = self.client.get(reverse('group_list') + '?q=B')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'BiPC Group')

    def test_group_delete_get_request_rejected(self):
        res = self.client.get(reverse('group_delete', args=[self.grp1.pk]))
        self.assertEqual(res.status_code, 405)
        self.assertTrue(Group.objects.filter(pk=self.grp1.pk).exists())

    def test_section_delete_get_request_rejected(self):
        res = self.client.get(reverse('section_delete', args=[self.sec1.pk]))
        self.assertEqual(res.status_code, 405)
        self.assertTrue(Section.objects.filter(pk=self.sec1.pk).exists())

    def test_group_delete_with_students_blocked(self):
        Student.objects.create(
            admission_number='ST101', name='John Doe', section=self.sec1, academic_year=self.ay
        )
        res = self.client.post(reverse('group_delete', args=[self.grp1.pk]), follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Cannot delete group')
        self.assertTrue(Group.objects.filter(pk=self.grp1.pk).exists())
        self.assertTrue(Student.objects.filter(admission_number='ST101').exists())

    def test_section_delete_with_students_blocked(self):
        Student.objects.create(
            admission_number='ST102', name='Jane Doe', section=self.sec1, academic_year=self.ay
        )
        res = self.client.post(reverse('section_delete', args=[self.sec1.pk]), follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Cannot delete section')
        self.assertTrue(Section.objects.filter(pk=self.sec1.pk).exists())
        self.assertTrue(Student.objects.filter(admission_number='ST102').exists())

    def test_empty_group_and_section_delete_succeeds(self):
        sec_pk = self.sec1.pk
        res_sec = self.client.post(reverse('section_delete', args=[sec_pk]), follow=True)
        self.assertEqual(res_sec.status_code, 200)
        self.assertFalse(Section.objects.filter(pk=sec_pk).exists())

        grp_pk = self.grp1.pk
        res_grp = self.client.post(reverse('group_delete', args=[grp_pk]), follow=True)
        self.assertEqual(res_grp.status_code, 200)
        self.assertFalse(Group.objects.filter(pk=grp_pk).exists())
