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


class GroupDeleteTestCase(TestCase):
    def setUp(self):
        from accounts.models import Group, Section, AcademicYear
        from students.models import Student
        from attendance.models import Attendance
        from datetime import date

        self.admin = User.objects.create_user(
            username='admin_grp_del', password='Password123!', role='admin', is_superuser=True
        )
        self.client = Client()
        self.client.force_login(self.admin)

        self.year = AcademicYear.objects.create(name='2024-2025', start_date=date(2024, 6, 1), end_date=date(2025, 5, 31))
        self.group = Group.objects.create(name='Test MPC', code='TMPC', academic_year=self.year)
        self.section = Section.objects.create(group=self.group, year='1', name='A', academic_year=self.year)
        self.student = Student.objects.create(
            admission_number='DEL101', name='Delete Me', mobile='9876543210', section=self.section, academic_year=self.year
        )
        self.attendance = Attendance.objects.create(student=self.student, date=date.today(), status='P')

    def test_get_group_delete_fails(self):
        res = self.client.get(reverse('group_delete', args=[self.group.pk]))
        self.assertEqual(res.status_code, 302)
        from accounts.models import Group
        self.assertTrue(Group.objects.filter(pk=self.group.pk).exists())

    def test_post_group_delete_deletes_all_related(self):
        from accounts.models import Group, Section
        from students.models import Student
        from attendance.models import Attendance

        res = self.client.post(reverse('group_delete', args=[self.group.pk]))
        self.assertEqual(res.status_code, 302)
        self.assertFalse(Group.objects.filter(pk=self.group.pk).exists())
        self.assertFalse(Section.objects.filter(pk=self.section.pk).exists())
        self.assertFalse(Student.objects.filter(pk=self.student.pk).exists())
        self.assertFalse(Attendance.objects.filter(pk=self.attendance.pk).exists())


