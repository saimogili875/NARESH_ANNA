from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User, AcademicYear, Group
from marks.models import Subject, ExamType, ExamCategory, GroupCategoryConfig, Exam, ExamSubjectMaxMark, Mark
from marks.views import get_subjects_for_exam, get_subject_max_marks
from marks.admin import ExamCategoryAdmin, GroupCategoryConfigInline

class SubjectAllotmentTestCase(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2025-2026", is_active=True,
            start_date=date(2025, 6, 1), end_date=date(2026, 5, 31)
        )
        self.group, _ = Group.objects.get_or_create(code="MPC", defaults={'name': "MPC", 'academic_year': self.year})
        self.category = ExamCategory.objects.create(name="IPE", is_fixed_marks=False)
        self.config = GroupCategoryConfig.objects.create(group=self.group, category=self.category)
        self.subject1 = Subject.objects.create(name="Physics")
        self.subject2 = Subject.objects.create(name="Maths")
        self.category.subjects.add(self.subject1, self.subject2)

        self.exam_type = ExamType.objects.create(name="Unit Test 1")
        self.exam = Exam.objects.create(
            exam_type=self.exam_type,
            academic_year=self.year,
            group=self.group,
            category=self.category,
            date=date.today(),
            max_marks=200,
        )

        self.admin_user = User.objects.create(
            username="admin_test_user", role="ADMIN", is_staff=True, is_superuser=True
        )
        self.admin_user.set_password("password123")
        self.admin_user.save()
        self.client = Client()
        self.client.force_login(self.admin_user)

    def test_get_subjects_for_exam(self):
        subs = get_subjects_for_exam(self.exam)
        self.assertEqual(len(subs), 2)
        self.assertIn(self.subject1, subs)
        self.assertIn(self.subject2, subs)

    def test_excluded_subjects_for_specific_exam_instance(self):
        subs = get_subjects_for_exam(self.exam)
        self.assertEqual(len(subs), 2)

        # Exclude subject2 for this specific exam instance only
        self.exam.excluded_subjects.add(self.subject2)
        subs_after = get_subjects_for_exam(self.exam)
        self.assertEqual(len(subs_after), 1)
        self.assertIn(self.subject1, subs_after)
        self.assertNotIn(self.subject2, subs_after)

        # Verify master category subjects remain untouched for future exams
        self.assertEqual(self.category.subjects.count(), 2)

    def test_get_subjects_for_exam_without_category(self):
        # Exam with no category should return empty list, not all subjects
        exam_no_cat = Exam(exam_type=self.exam_type, academic_year=self.year, date=date.today())
        subjects = get_subjects_for_exam(exam_no_cat)
        self.assertEqual(subjects, [])

    def test_get_subject_max_marks(self):
        ExamSubjectMaxMark.objects.create(exam=self.exam, subject=self.subject1, max_marks=75)
        subjects = get_subjects_for_exam(self.exam)
        max_marks_map = get_subject_max_marks(self.exam, subjects)
        self.assertEqual(max_marks_map[self.subject1], 75)
        self.assertEqual(max_marks_map[self.subject2], 200) # fallback to exam.max_marks

    def test_exam_add_creates_max_marks(self):
        url = reverse('exam_add')
        response = self.client.post(url, {
            'exam_type': self.exam_type.id,
            'group_id': self.group.id,
            'category': self.category.id,
            'date': '2026-08-15',
            'subject_max_Physics': '75',
            'subject_max_Maths': '100',
        })
        self.assertEqual(response.status_code, 302)
        new_exam = Exam.objects.order_by('-id').first()
        self.assertEqual(new_exam.category, self.category)
        self.assertEqual(new_exam.max_marks, 175)
        
        max1 = ExamSubjectMaxMark.objects.get(exam=new_exam, subject=self.subject1)
        max2 = ExamSubjectMaxMark.objects.get(exam=new_exam, subject=self.subject2)
        self.assertEqual(max1.max_marks, 75)
        self.assertEqual(max2.max_marks, 100)

    def test_exam_add_validation_unconfigured_group(self):
        other_group = Group.objects.create(name="BPC", code="BPC", academic_year=self.year)
        url = reverse('exam_add')
        response = self.client.post(url, {
            'exam_type': self.exam_type.id,
            'group_id': other_group.id,
            'category': self.category.id,
            'date': '2026-08-15',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'is not configured for group')

    def test_exam_add_validation_category_without_subjects(self):
        empty_cat = ExamCategory.objects.create(name="Empty Cat")
        GroupCategoryConfig.objects.create(group=self.group, category=empty_cat)
        url = reverse('exam_add')
        response = self.client.post(url, {
            'exam_type': self.exam_type.id,
            'group_id': self.group.id,
            'category': empty_cat.id,
            'date': '2026-08-15',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'has no subjects attached')

    def test_admin_inline_registration(self):
        self.assertIn(GroupCategoryConfigInline, ExamCategoryAdmin.inlines)

    def test_faculty_subject_access_control(self):
        from faculty.models import Faculty
        fac_user = User.objects.create(username="fac_user", role="faculty")
        fac_user.set_password("pass")
        fac_user.save()
        fac_profile = Faculty.objects.create(
            user=fac_user, employee_id="FAC-99", name="Test Faculty",
            subject="Physics", phone="9999999999", email="fac@test.com",
            date_of_joining=date.today()
        )
        fac_profile.assigned_subjects.add(self.subject1) # Only Physics, not Maths

        self.client.force_login(fac_user)
        url = reverse('marks_entry', args=[self.exam.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        entry_subjects = response.context['subjects']
        self.assertEqual(len(entry_subjects), 1)
        self.assertEqual(entry_subjects[0], self.subject1)

        report_url = reverse('marks_report') + f"?section=all&exam={self.exam.id}"
        response_report = self.client.get(report_url)
        self.assertEqual(response_report.status_code, 200)
        report_subjects = response_report.context['subjects']
        self.assertEqual(len(report_subjects), 1)
        self.assertEqual(report_subjects[0], self.subject1)

    def test_marks_entry_submit_once_and_lock(self):
        from faculty.models import Faculty
        from accounts.models import Section
        from students.models import Student
        from marks.models import MarksEntryLock

        section = Section.objects.create(group=self.group, year="1", name="A", academic_year=self.year)
        student = Student.objects.create(
            admission_number="STU-999", name="Test Student", father_name="Parent",
            mobile="9999999999", section=section, academic_year=self.year, is_active=True
        )

        fac_user = User.objects.create(username="fac_user_lock", role="faculty")
        fac_user.set_password("pass")
        fac_user.save()
        fac_profile = Faculty.objects.create(
            user=fac_user, employee_id="FAC-100", name="Faculty Lock Test",
            subject="Physics", phone="9999999999", email="fac_lock@test.com",
            date_of_joining=date.today()
        )
        fac_profile.assigned_subjects.add(self.subject1)
        fac_profile.assigned_sections.add(section)

        # 1. Faculty saves marks -> creates lock
        self.client.force_login(fac_user)
        entry_url = reverse('marks_entry', args=[self.exam.id])
        post_data = {
            'section_id': section.id,
            f'mark_{student.pk}_Physics': '88.5',
        }
        res = self.client.post(entry_url, post_data)
        self.assertEqual(res.status_code, 302)

        mark = Mark.objects.get(student=student, exam=self.exam, subject=self.subject1)
        self.assertEqual(float(mark.marks_obtained), 88.5)

        lock = MarksEntryLock.objects.get(exam=self.exam, section=section, subject=self.subject1)
        self.assertTrue(lock.is_locked)

        # 2. Faculty tries to overwrite locked mark -> rejected by server-side check
        post_data_tampered = {
            'section_id': section.id,
            f'mark_{student.pk}_Physics': '99.0',
        }
        res_tampered = self.client.post(entry_url, post_data_tampered)
        self.assertEqual(res_tampered.status_code, 302)

        mark.refresh_from_db()
        self.assertEqual(float(mark.marks_obtained), 88.5) # Unchanged!

        # 3. Admin unlocks the subject
        self.client.force_login(self.admin_user)
        unlock_url = reverse('marks_entry_unlock', args=[self.exam.id, section.id, self.subject1.id])
        res_unlock = self.client.get(unlock_url)
        self.assertEqual(res_unlock.status_code, 302)

        lock.refresh_from_db()
        self.assertFalse(lock.is_locked)

    def test_whatsapp_send_flow(self):
        from accounts.models import Section
        from students.models import Student
        from marks.models import MarksEntryLock, MarksWhatsAppSendLog
        from marks.views import get_section_completion_status
        from whatsapp.models import PendingMessage

        section = Section.objects.create(group=self.group, year="1", name="B", academic_year=self.year)
        student = Student.objects.create(
            admission_number="STU-1000", name="WhatsApp Student", father_name="Parent",
            mobile="9876543210", section=section, academic_year=self.year, is_active=True
        )
        Mark.objects.create(student=student, exam=self.exam, subject=self.subject1, marks_obtained=90)
        Mark.objects.create(student=student, exam=self.exam, subject=self.subject2, marks_obtained=85)

        # 1. Locks not present -> incomplete
        statuses = get_section_completion_status(self.exam)
        sec_status = next(s for s in statuses if s['section'] == section)
        self.assertFalse(sec_status['is_complete'])

        # 2. Lock both subjects -> complete
        MarksEntryLock.objects.create(exam=self.exam, section=section, subject=self.subject1, is_locked=True)
        MarksEntryLock.objects.create(exam=self.exam, section=section, subject=self.subject2, is_locked=True)

        statuses = get_section_completion_status(self.exam)
        sec_status = next(s for s in statuses if s['section'] == section)
        self.assertTrue(sec_status['is_complete'])
        self.assertFalse(sec_status['is_sent'])

        # 3. GET whatsapp send view as admin
        self.client.force_login(self.admin_user)
        send_url = reverse('marks_whatsapp_send', args=[self.exam.id])
        res = self.client.get(send_url)
        self.assertEqual(res.status_code, 200)

        # 4. POST to queue section
        res_post = self.client.post(send_url, {'selected_sections': [section.id]})
        self.assertEqual(res_post.status_code, 302)

        # Verify PendingMessage created
        msg = PendingMessage.objects.filter(student=student).first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.phone, "9876543210")
        self.assertIn("WhatsApp Student", msg.message)
        self.assertIn("Physics: 90", msg.message)

        # Verify MarksWhatsAppSendLog created
        log = MarksWhatsAppSendLog.objects.filter(exam=self.exam, section=section).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.student_count, 1)

        # Re-query completion status -> now sent
        statuses = get_section_completion_status(self.exam)
        sec_status = next(s for s in statuses if s['section'] == section)
        self.assertTrue(sec_status['is_sent'])

    def test_admin_marks_entry_creates_locks(self):
        from accounts.models import Section
        from students.models import Student
        from marks.models import MarksEntryLock

        section = Section.objects.create(group=self.group, year="1", name="C", academic_year=self.year)
        student = Student.objects.create(
            admission_number="STU-1001", name="Admin Entry Student", father_name="Parent",
            mobile="9876543211", section=section, academic_year=self.year, is_active=True
        )

        # Admin logs in and saves marks for Physics & Maths
        self.client.force_login(self.admin_user)
        entry_url = reverse('marks_entry', args=[self.exam.id])
        post_data = {
            'section_id': section.id,
            f'mark_{student.pk}_Physics': '92',
            f'mark_{student.pk}_Maths': '96',
        }
        res = self.client.post(entry_url, post_data)
        self.assertEqual(res.status_code, 302)

        # Verify marks saved
        m_phys = Mark.objects.get(student=student, exam=self.exam, subject=self.subject1)
        m_math = Mark.objects.get(student=student, exam=self.exam, subject=self.subject2)
        self.assertEqual(float(m_phys.marks_obtained), 92.0)
        self.assertEqual(float(m_math.marks_obtained), 96.0)

        # Verify MarksEntryLock created for both subjects by Admin
        lock1 = MarksEntryLock.objects.get(exam=self.exam, section=section, subject=self.subject1)
        lock2 = MarksEntryLock.objects.get(exam=self.exam, section=section, subject=self.subject2)
        self.assertTrue(lock1.is_locked)
        self.assertTrue(lock2.is_locked)
        self.assertEqual(lock1.locked_by, self.admin_user)

    def test_exam_edit_and_delete(self):
        # Test editing exam date and max marks
        edit_url = reverse('exam_edit', args=[self.exam.id])
        res_edit = self.client.post(edit_url, {
            'date': '2026-09-15',
            f'subject_max_{self.subject1.name}': '100',
            f'subject_max_{self.subject2.name}': '100',
        })
        self.assertEqual(res_edit.status_code, 302)
        self.exam.refresh_from_db()
        self.assertEqual(str(self.exam.date), '2026-09-15')

        # Test deleting exam confirmation page and POST delete
        delete_url = reverse('exam_delete', args=[self.exam.id])
        res_get = self.client.get(delete_url)
        self.assertEqual(res_get.status_code, 200)
        res_del = self.client.post(delete_url)
        self.assertEqual(res_del.status_code, 302)
        self.assertFalse(Exam.objects.filter(pk=self.exam.id).exists())

    def test_whatsapp_resend_allowed(self):
        from accounts.models import Section
        from marks.models import MarksWhatsAppSendLog
        section = Section.objects.create(group=self.group, year="1", name="WA-1", academic_year=self.year)
        
        # Mark as sent initially
        MarksWhatsAppSendLog.objects.create(exam=self.exam, section=section, sent_by=self.admin_user, student_count=1)

        wa_url = reverse('marks_whatsapp_send', args=[self.exam.id])
        res_get = self.client.get(wa_url)
        self.assertEqual(res_get.status_code, 200)
        self.assertContains(res_get, 'Sent (Click to Resend)')

    def test_faculty_section_idor_blocked(self):
        from faculty.models import Faculty
        from accounts.models import Section
        from students.models import Student

        sec_allowed = Section.objects.create(group=self.group, year="1", name="A1", academic_year=self.year)
        sec_disallowed = Section.objects.create(group=self.group, year="1", name="B1", academic_year=self.year)

        student = Student.objects.create(
            admission_number="STU-IDOR", name="IDOR Student", father_name="Parent",
            mobile="9999999999", section=sec_disallowed, academic_year=self.year, is_active=True
        )

        fac_user = User.objects.create(username="fac_idor_user", role="faculty")
        fac_user.set_password("pass123")
        fac_user.save()

        fac_profile = Faculty.objects.create(
            user=fac_user, employee_id="FAC-IDOR", name="Faculty IDOR Test",
            subject="Physics", phone="9999999999", email="fac_idor@test.com",
            date_of_joining=date.today()
        )
        fac_profile.assigned_subjects.add(self.subject1)
        fac_profile.assigned_sections.add(sec_allowed)

        self.client.force_login(fac_user)

        # 1. Attempt POST marks for disallowed section -> blocked, 0 marks created
        entry_url = reverse('marks_entry', args=[self.exam.id])
        post_data = {
            'section_id': sec_disallowed.id,
            f'mark_{student.pk}_Physics': '95.0',
        }
        res = self.client.post(entry_url, post_data)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(Mark.objects.filter(student=student).count(), 0)

        # 2. Attempt GET marks_report for disallowed section -> blocked with Access denied
        report_url = reverse('marks_report') + f"?section={sec_disallowed.id}&exam={self.exam.id}"
        res_report = self.client.get(report_url, follow=True)
        self.assertContains(res_report, 'Access denied')

    def test_conc_202_marks_entry_atomic_locking(self):
        from accounts.models import Section
        from students.models import Student
        sec = Section.objects.create(group=self.group, year="1", name="C1", academic_year=self.year)
        stu = Student.objects.create(admission_number="CONC001", name="Conc Student", section=sec, academic_year=self.year, is_active=True)

        entry_url = reverse('marks_entry', args=[self.exam.id])
        post_data = {
            'section_id': sec.id,
            f'mark_{stu.pk}_{self.subject1.name}': '85.0',
        }
        res = self.client.post(entry_url, post_data)
        self.assertEqual(res.status_code, 302)
        mark = Mark.objects.get(student=stu, exam=self.exam, subject=self.subject1)
        self.assertEqual(float(mark.marks_obtained), 85.0)






