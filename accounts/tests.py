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

    def test_invalid_captcha_returns_200_not_500(self):
        hashkey = CaptchaStore.generate_key()
        res = self.client.post(reverse('login'), {
            'username': 'admin_audit',
            'password': 'Password123!',
            'human_typed': 'true',
            'captcha_0': hashkey,
            'captcha_1': 'WRONG_CAPTCHA',
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Invalid CAPTCHA')

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

    def test_user_toggle_get_request_rejected(self):
        target_user = User.objects.create_user(username='target_toggle', password='Pass123!', role='staff')
        initial_status = target_user.is_active
        res = self.client.get(reverse('user_toggle', args=[target_user.pk]))
        self.assertEqual(res.status_code, 405)
        target_user.refresh_from_db()
        self.assertEqual(target_user.is_active, initial_status)

    def test_user_reset_password_blank_invalid_rejected(self):
        target_user = User.objects.create_user(username='target_reset', password='OldPass123!', role='staff')
        # Test blank password
        res_blank = self.client.post(reverse('user_reset_password', args=[target_user.pk]), {'password': '   '})
        self.assertEqual(res_blank.status_code, 200)
        self.assertContains(res_blank, 'Password cannot be blank')
        self.assertTrue(target_user.check_password('OldPass123!'))

        # Test common/weak password (violates Django validation rules)
        res_weak = self.client.post(reverse('user_reset_password', args=[target_user.pk]), {'password': '123'})
        self.assertEqual(res_weak.status_code, 200)
        self.assertTrue(target_user.check_password('OldPass123!'))

    def test_missing_credentials_rejection_no_failed_log_or_axes_lockout(self):
        anon_client = Client()
        initial_log_count = LoginLog.objects.filter(username='admin_autofill', status='FAILED').count()
        res = anon_client.post(reverse('login'), {
            'username': '',
            'password': '',
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Please enter both username and password')
        new_log_count = LoginLog.objects.filter(username='admin_autofill', status='FAILED').count()
        self.assertEqual(new_log_count, initial_log_count)



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


from django.test import override_settings

class IPWhitelistMiddlewareTestCase(TestCase):
    @override_settings(
        ALLOWED_CLIENT_IPS=['1.2.3.4'],
        TRUSTED_PROXY_IPS=['10.0.0.1'],
        IP_WHITELIST_EXEMPT_PATHS=['/healthz']
    )
    def test_ip_whitelisting_behind_trusted_proxy(self):
        res_allowed = self.client.get('/login/', REMOTE_ADDR='10.0.0.1', HTTP_X_FORWARDED_FOR='1.2.3.4')
        self.assertEqual(res_allowed.status_code, 200)

        res_blocked = self.client.get('/login/', REMOTE_ADDR='10.0.0.1', HTTP_X_FORWARDED_FOR='5.6.7.8')
        self.assertEqual(res_blocked.status_code, 403)


class SecuritySettingsTestCase(TestCase):
    @override_settings(
        DEBUG=False,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_SSL_REDIRECT=False,
    )
    def test_secure_cookies_in_production_settings(self):
        res = self.client.get('/login/', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(res.status_code, 200)
        self.assertIn('csrftoken', res.cookies)
        self.assertTrue(res.cookies['csrftoken']['secure'])


from unittest.mock import patch
from django.contrib.messages.storage.fallback import FallbackStorage
from accounts.admin import GroupAdmin, SectionAdmin
from django.contrib.admin.sites import AdminSite


class GroupDeletionRulesTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_del_test', password='Password123!', role='admin', is_staff=True, is_superuser=True
        )
        self.staff = User.objects.create_user(
            username='staff_del_test', password='Password123!', role='faculty', is_staff=False, is_superuser=False
        )
        self.client = Client()
        self.client.force_login(self.admin)
        self.ay = AcademicYear.objects.create(
            name='2024-2025', is_active=True, start_date='2024-06-01', end_date='2025-05-31'
        )

    def test_group_with_0_sections_and_0_students_deletes(self):
        grp = Group.objects.create(name='EmptyGroup', code='EMPTY1', academic_year=self.ay)
        res = self.client.post(reverse('group_delete', args=[grp.pk]), follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Group.objects.filter(pk=grp.pk).exists())

    def test_group_with_sections_and_0_students_needs_confirm(self):
        grp = Group.objects.create(name='GroupWithSec', code='GWSEC1', academic_year=self.ay)
        sec = Section.objects.create(group=grp, year='1', name='A', academic_year=self.ay)
        
        # Unconfirmed delete should fail and keep group + section
        res_unconfirmed = self.client.post(reverse('group_delete', args=[grp.pk]), follow=True)
        self.assertEqual(res_unconfirmed.status_code, 200)
        self.assertContains(res_unconfirmed, 'requires confirmation')
        self.assertTrue(Group.objects.filter(pk=grp.pk).exists())
        self.assertTrue(Section.objects.filter(pk=sec.pk).exists())

        # Confirmed delete (confirm=1) should delete section and group
        res_confirmed = self.client.post(reverse('group_delete', args=[grp.pk]), {'confirm': '1'}, follow=True)
        self.assertEqual(res_confirmed.status_code, 200)
        self.assertContains(res_confirmed, 'deleted successfully')
        self.assertFalse(Group.objects.filter(pk=grp.pk).exists())
        self.assertFalse(Section.objects.filter(pk=sec.pk).exists())

    def test_group_with_only_inactive_students_is_blocked(self):
        grp = Group.objects.create(name='InactiveGroup', code='INACT1', academic_year=self.ay)
        sec = Section.objects.create(group=grp, year='1', name='A', academic_year=self.ay)
        Student.objects.create(
            admission_number='INACT_01', name='Inactive Sam', section=sec, academic_year=self.ay, is_active=False
        )

        res = self.client.post(reverse('group_delete', args=[grp.pk]), {'confirm': '1'}, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Cannot delete group')
        self.assertContains(res, '0 active, 1 inactive')
        self.assertTrue(Group.objects.filter(pk=grp.pk).exists())
        self.assertTrue(Section.objects.filter(pk=sec.pk).exists())

    def test_group_with_active_students_is_blocked(self):
        grp = Group.objects.create(name='ActiveGroup', code='ACT1', academic_year=self.ay)
        sec = Section.objects.create(group=grp, year='1', name='A', academic_year=self.ay)
        Student.objects.create(
            admission_number='ACT_01', name='Active Alice', section=sec, academic_year=self.ay, is_active=True
        )

        res = self.client.post(reverse('group_delete', args=[grp.pk]), {'confirm': '1'}, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Cannot delete group')
        self.assertTrue(Group.objects.filter(pk=grp.pk).exists())
        self.assertTrue(Section.objects.filter(pk=sec.pk).exists())

    def test_section_with_students_is_blocked(self):
        grp = Group.objects.create(name='SecGroup', code='SECGRP', academic_year=self.ay)
        sec = Section.objects.create(group=grp, year='1', name='A', academic_year=self.ay)
        Student.objects.create(
            admission_number='SEC_01', name='Section Student', section=sec, academic_year=self.ay, is_active=True
        )

        res = self.client.post(reverse('section_delete', args=[sec.pk]), follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Cannot delete section')
        self.assertTrue(Section.objects.filter(pk=sec.pk).exists())

    def test_non_admin_user_gets_denied(self):
        self.client.force_login(self.staff)
        grp = Group.objects.create(name='NonAdminGroup', code='NADMIN', academic_year=self.ay)
        res = self.client.post(reverse('group_delete', args=[grp.pk]), {'confirm': '1'})
        self.assertNotEqual(res.status_code, 200)
        self.assertTrue(Group.objects.filter(pk=grp.pk).exists())

    def test_get_request_to_delete_url_rejected(self):
        grp = Group.objects.create(name='GetGroup', code='GETGRP', academic_year=self.ay)
        res = self.client.get(reverse('group_delete', args=[grp.pk]))
        self.assertEqual(res.status_code, 405)
        self.assertTrue(Group.objects.filter(pk=grp.pk).exists())

    def test_no_raw_protected_error_text_in_messages(self):
        grp = Group.objects.create(name='RawErrGroup', code='RAWERR', academic_year=self.ay)
        sec = Section.objects.create(group=grp, year='1', name='A', academic_year=self.ay)
        Student.objects.create(
            admission_number='RAW_01', name='Raw Student', section=sec, academic_year=self.ay, is_active=True
        )
        res = self.client.post(reverse('group_delete', args=[grp.pk]), {'confirm': '1'}, follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, 'ProtectedError')
        self.assertNotContains(res, 'Cannot delete group. Deleting the selected group would require')

    def test_admin_bulk_delete_respects_rules(self):
        site = AdminSite()
        admin_obj = GroupAdmin(Group, site)
        
        # 1. Group with students -> blocked
        grp_students = Group.objects.create(name='AdminGrp1', code='AGRP1', academic_year=self.ay)
        sec1 = Section.objects.create(group=grp_students, year='1', name='A', academic_year=self.ay)
        Student.objects.create(admission_number='AG1', name='Ag Student', section=sec1, academic_year=self.ay)

        # 2. Group with sections (0 students) -> blocked with clear warning message
        grp_sections = Group.objects.create(name='AdminGrp2', code='AGRP2', academic_year=self.ay)
        Section.objects.create(group=grp_sections, year='1', name='A', academic_year=self.ay)

        # 3. Group with 0 sections & 0 students -> deletes
        grp_empty = Group.objects.create(name='AdminGrp3', code='AGRP3', academic_year=self.ay)

        req = self.client.get('/').wsgi_request
        req.user = self.admin
        setattr(req, '_messages', FallbackStorage(req))

        admin_obj.delete_queryset(req, Group.objects.filter(pk__in=[grp_students.pk, grp_sections.pk, grp_empty.pk]))

        self.assertTrue(Group.objects.filter(pk=grp_students.pk).exists())
        self.assertTrue(Group.objects.filter(pk=grp_sections.pk).exists())
        self.assertFalse(Group.objects.filter(pk=grp_empty.pk).exists())

    def test_transaction_rollback_on_failure(self):
        grp = Group.objects.create(name='RollbackGroup', code='RBACK', academic_year=self.ay)
        sec = Section.objects.create(group=grp, year='1', name='A', academic_year=self.ay)

        with patch.object(Group, 'delete', side_effect=Exception("Database failure during group delete")):
            res = self.client.post(reverse('group_delete', args=[grp.pk]), {'confirm': '1'}, follow=True)
            self.assertEqual(res.status_code, 200)
            self.assertContains(res, 'An unexpected error occurred')

        # Because transaction.atomic() rolled back, section MUST still exist!
        self.assertTrue(Group.objects.filter(pk=grp.pk).exists())
        self.assertTrue(Section.objects.filter(pk=sec.pk).exists())



