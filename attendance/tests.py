from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
import json
from accounts.models import User, AcademicYear, Group, Section
from students.models import Student
from attendance.models import Attendance
from whatsapp.models import PendingMessage


class AttendanceFeaturesTest(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(name='2026-2027', start_date='2026-06-01', end_date='2027-05-31', is_active=True)
        self.admin = User.objects.create_user(username='admin_user', password='password123', role='admin')
        self.group, _ = Group.objects.get_or_create(code='MPC', defaults={'name': 'MPC', 'academic_year': self.year})
        self.section = Section.objects.create(group=self.group, year='1', name='A', academic_year=self.year)

        self.student1 = Student.objects.create(name='Student 1', admission_number='ATT001', section=self.section, academic_year=self.year, mobile='9876543210')
        self.student2 = Student.objects.create(name='Student 2', admission_number='ATT002', section=self.section, academic_year=self.year, mobile='9876543211')

        self.client = Client()
        self.client.force_login(self.admin)

    def test_perf_201_edge_201_async_reasons_and_queue_count(self):
        today = timezone.localdate()
        Attendance.objects.create(student=self.student1, section=self.section, date=today, status='A')
        Attendance.objects.create(student=self.student2, section=self.section, date=today, status='A')

        res = self.client.post(reverse('attendance_save_reasons'), {
            'section_id': self.section.pk,
            'date': today.isoformat(),
            f'reason_{self.student1.pk}': 'health',
            f'reason_{self.student2.pk}': 'went_out',
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('queued_count'), 2)
        self.assertEqual(PendingMessage.objects.filter(status=PendingMessage.STATUS_PENDING).count(), 2)

    def test_err_201_tap_mark_api_safe_error(self):
        # Invalid payload causing error does not leak str(e) exception details
        res = self.client.post(reverse('attendance_tap_mark_api'), data={'student_id': 'invalid_id'}, content_type='application/json')
        self.assertIn(res.status_code, (400, 500))
        data = res.json()
        self.assertFalse(data.get('success'))
        self.assertNotIn('Traceback', data.get('error', ''))
        self.assertNotIn('Exception', data.get('error', ''))

    def test_tap_mark_api_date_and_status_validation(self):
        # Create an open attendance window for testing
        from datetime import time
        from attendance.models import AttendanceWindow
        AttendanceWindow.objects.create(is_active=True, start_time=time(0, 0), end_time=time(23, 59, 59))

        # Valid date (today) + valid status ('P')
        today = timezone.localdate()
        res_valid = self.client.post(
            reverse('attendance_tap_mark_api'),
            data=json.dumps({
                'student_id': self.student1.pk,
                'section_id': self.section.pk,
                'date': today.isoformat(),
                'status': 'P'
            }),
            content_type='application/json'
        )
        self.assertEqual(res_valid.status_code, 200)

        # Invalid date (yesterday)
        yesterday = today - timezone.timedelta(days=1)
        res_yesterday = self.client.post(
            reverse('attendance_tap_mark_api'),
            data=json.dumps({
                'student_id': self.student1.pk,
                'section_id': self.section.pk,
                'date': yesterday.isoformat(),
                'status': 'P'
            }),
            content_type='application/json'
        )
        self.assertEqual(res_yesterday.status_code, 400)

        # Invalid date (future date)
        tomorrow = today + timezone.timedelta(days=1)
        res_future = self.client.post(
            reverse('attendance_tap_mark_api'),
            data=json.dumps({
                'student_id': self.student1.pk,
                'section_id': self.section.pk,
                'date': tomorrow.isoformat(),
                'status': 'P'
            }),
            content_type='application/json'
        )
        self.assertEqual(res_future.status_code, 400)

        # Malformed date
        res_malformed = self.client.post(
            reverse('attendance_tap_mark_api'),
            data=json.dumps({
                'student_id': self.student1.pk,
                'section_id': self.section.pk,
                'date': '2026-99-99',
                'status': 'P'
            }),
            content_type='application/json'
        )
        self.assertEqual(res_malformed.status_code, 400)

        # Missing date
        res_missing = self.client.post(
            reverse('attendance_tap_mark_api'),
            data=json.dumps({
                'student_id': self.student1.pk,
                'section_id': self.section.pk,
                'date': '',
                'status': 'P'
            }),
            content_type='application/json'
        )
        self.assertEqual(res_missing.status_code, 400)

        # Valid status ('A')
        res_valid_a = self.client.post(
            reverse('attendance_tap_mark_api'),
            data=json.dumps({
                'student_id': self.student1.pk,
                'section_id': self.section.pk,
                'date': today.isoformat(),
                'status': 'A'
            }),
            content_type='application/json'
        )
        self.assertEqual(res_valid_a.status_code, 200)

        # Invalid status ('INVALID')
        res_invalid_status = self.client.post(
            reverse('attendance_tap_mark_api'),
            data=json.dumps({
                'student_id': self.student1.pk,
                'section_id': self.section.pk,
                'date': today.isoformat(),
                'status': 'INVALID'
            }),
            content_type='application/json'
        )
        self.assertEqual(res_invalid_status.status_code, 400)
