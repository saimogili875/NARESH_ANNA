from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
import openpyxl
import io
from accounts.models import User, AcademicYear, Group, Section
from students.models import Student
from faculty.models import Faculty


class StudentAuthorizationAndImportTest(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(name='2026-2027', start_date='2026-06-01', end_date='2027-05-31', is_active=True)
        self.admin = User.objects.create_user(username='admin_user', password='password123', role='admin')
        self.group, _ = Group.objects.get_or_create(code='MPC', defaults={'name': 'MPC', 'academic_year': self.year})
        self.sec_a = Section.objects.create(group=self.group, year='1', name='A', academic_year=self.year)
        self.sec_b = Section.objects.create(group=self.group, year='1', name='B', academic_year=self.year)

        self.student_a = Student.objects.create(name='Student Alpha', admission_number='ADM001', section=self.sec_a, academic_year=self.year, mobile='9876543210')
        self.student_b = Student.objects.create(name='Student Beta', admission_number='ADM002', section=self.sec_b, academic_year=self.year, mobile='9876543211')

        self.fac_user = User.objects.create_user(username='fac_user', password='password123', role='faculty')
        self.fac_profile = Faculty.objects.create(user=self.fac_user, employee_id='EMP101', name='Faculty SecA', subject='Physics', phone='9999999999', date_of_joining=timezone.localdate())
        self.fac_profile.assigned_sections.add(self.sec_a)

        self.client = Client()

    def test_sec_204_student_list_faculty_authorization(self):
        self.client.force_login(self.fac_user)
        # Faculty assigned to Sec A should see Student Alpha, but not Student Beta
        res = self.client.get(reverse('student_list'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Student Alpha')
        self.assertNotContains(res, 'Student Beta')

        # Searching for Student Beta (mobile/name) should return no results for Faculty A
        res_search = self.client.get(reverse('student_list') + '?q=Beta')
        self.assertEqual(res_search.status_code, 200)
        self.assertNotContains(res_search, 'Student Beta')

    def test_file_201_student_import_excel_limits(self):
        self.client.force_login(self.admin)

        # 1. Oversized file (> 5 MB)
        large_content = b'x' * (5 * 1024 * 1024 + 100)
        large_file = SimpleUploadedFile("large.xlsx", large_content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        res_large = self.client.post(reverse('student_import'), {'file': large_file})
        self.assertEqual(res_large.status_code, 302)

        # 2. Workbook with too many sheets (> 10 sheets)
        wb_sheets = openpyxl.Workbook()
        for i in range(11):
            wb_sheets.create_sheet(f"Sheet_{i}")
        out_sheets = io.BytesIO()
        wb_sheets.save(out_sheets)
        out_sheets.seek(0)
        file_sheets = SimpleUploadedFile("too_many_sheets.xlsx", out_sheets.read(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        res_sheets = self.client.post(reverse('student_import'), {'file': file_sheets})
        self.assertEqual(res_sheets.status_code, 302)

    def test_protected_media_access(self):
        # Anonymous access to media should be denied
        anon_client = Client()
        res_anon = anon_client.get('/media/students/photos/test.jpg')
        self.assertEqual(res_anon.status_code, 401)

        # Logged in admin access
        self.client.force_login(self.admin)
        res_admin = self.client.get('/media/students/photos/test.jpg')
        self.assertEqual(res_admin.status_code, 404)  # 404 because file doesn't exist on disk, not 401/403

    def test_inline_update_safe_error(self):
        self.client.force_login(self.admin)
        # Attempt to set duplicate admission_number
        res = self.client.post(reverse('student_inline_update', args=[self.student_b.pk]), {
            'field': 'admission_number',
            'value': self.student_a.admission_number
        })
        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertFalse(data.get('ok'))
        self.assertNotIn('Traceback', data.get('error', ''))

    def test_get_client_ip_spoofing(self):
        from accounts.models import get_client_ip
        class Request:
            META = {
                'REMOTE_ADDR': '198.51.100.5',
                'HTTP_X_FORWARDED_FOR': '203.0.113.195, 198.51.100.5'
            }
        req = Request()
        ip = get_client_ip(req)
        # Without TRUSTED_PROXY_IPS configured, REMOTE_ADDR is returned to prevent spoofing
        self.assertEqual(ip, '198.51.100.5')
