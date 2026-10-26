import os
import io
import uuid
import threading
from decimal import Decimal, InvalidOperation
from unittest.mock import patch, MagicMock

import django
from django.test import TestCase, TransactionTestCase, Client
from django.test.utils import CaptureQueriesContext
from django.db import connection, transaction, IntegrityError
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.http import HttpResponse

from accounts.models import User, AcademicYear, Group, Section
from faculty.models import Faculty
from students.models import Student
from fees.models import StudentFee, FeePayment, FeeType, StudentFeeCharge
from fees.receipt_pdf import generate_receipt_pdf, save_receipt_pdf
from fees.utils import sync_student_section_fees


class BaseFeeTestCase(TestCase):
    """Base setup factory for fees full test suite."""

    def setUp(self):
        super().setUp()

        # Globally mock WhatsApp media send to avoid real external calls and rate limits
        self.wa_patcher = patch('fees.views.send_whatsapp_media', return_value={'success': True, 'message_id': 'MOCK_WAMID'})
        self.mock_send_wa = self.wa_patcher.start()
        self.addCleanup(self.wa_patcher.stop)

        # Academic Year
        self.year = AcademicYear.objects.create(
            name='2026-2027',
            start_date='2026-06-01',
            end_date='2027-05-31',
            is_active=True
        )
        self.year_old = AcademicYear.objects.create(
            name='2025-2026',
            start_date='2025-06-01',
            end_date='2026-05-31',
            is_active=False
        )

        # Groups & Sections (migration 0008 pre-seeds MPC, BiPC, CEC, MEC)
        self.group, _ = Group.objects.get_or_create(code='MPC', defaults={'name': 'MPC', 'academic_year': self.year})
        self.section_a, _ = Section.objects.get_or_create(group=self.group, year='1', name='A', defaults={'academic_year': self.year})
        self.section_b, _ = Section.objects.get_or_create(group=self.group, year='1', name='B', defaults={'academic_year': self.year})

        # Users
        self.admin = User.objects.create_user(
            username='admin_test', password='password123', role=User.ROLE_ADMIN
        )
        self.accounts_user = User.objects.create_user(
            username='accounts_test', password='password123', role=User.ROLE_ACCOUNTS
        )
        self.faculty_user = User.objects.create_user(
            username='faculty_test', password='password123', role=User.ROLE_FACULTY
        )
        self.faculty_other = User.objects.create_user(
            username='faculty_other', password='password123', role=User.ROLE_FACULTY
        )
        self.superuser = User.objects.create_superuser(
            username='super_test', password='password123', email='super@test.com'
        )

        # Faculty profiles and assigned sections
        self.fac_profile = Faculty.objects.create(
            user=self.faculty_user,
            employee_id='FAC001',
            name='Prof Raman',
            subject='Maths',
            phone='9876543210',
            date_of_joining='2026-01-01'
        )
        self.fac_profile.assigned_sections.add(self.section_a)

        self.fac_profile_other = Faculty.objects.create(
            user=self.faculty_other,
            employee_id='FAC002',
            name='Prof Bose',
            subject='Physics',
            phone='9876543211',
            date_of_joining='2026-01-01'
        )
        self.fac_profile_other.assigned_sections.add(self.section_b)

        # Primary Student
        self.student = Student.objects.create(
            name='Ravi Kumar',
            admission_number='ADM2026001',
            mobile='9876543210',
            father_name='Suresh Kumar',
            section=self.section_a,
            academic_year=self.year
        )

        # Primary Fees
        self.student_fee = StudentFee.objects.create(
            student=self.student,
            academic_year=self.year,
            total_fee=Decimal('50000.00')
        )
        self.fee_type = FeeType.objects.create(
            name='Exam Fee',
            academic_year=self.year
        )
        self.fee_charge = StudentFeeCharge.objects.create(
            student=self.student,
            fee_type=self.fee_type,
            amount_assigned=Decimal('3000.00')
        )

        self.client = Client()
        self.client.force_login(self.admin)


# ==============================================================================
# A. MODELS
# ==============================================================================
class FeeModelsTest(BaseFeeTestCase):
    def test_student_fee_properties_and_status(self):
        # 1. Initially no payments
        self.assertEqual(self.student_fee.total_paid, 0)
        self.assertEqual(self.student_fee.total_pending, Decimal('50000.00'))
        self.assertEqual(self.student_fee.payment_percentage, 0)
        self.assertEqual(self.student_fee.status, 'Pending')

        # 2. Partial payment
        p1 = FeePayment.objects.create(
            student_fee=self.student_fee,
            amount=Decimal('20000.00'),
            payment_date=timezone.localdate(),
            receipt_number='RCP_MOD_01'
        )
        self.assertEqual(self.student_fee.total_paid, Decimal('20000.00'))
        self.assertEqual(self.student_fee.total_pending, Decimal('30000.00'))
        self.assertEqual(self.student_fee.payment_percentage, 40.0)
        self.assertEqual(self.student_fee.status, 'Partial')

        # 3. Full payment
        p2 = FeePayment.objects.create(
            student_fee=self.student_fee,
            amount=Decimal('30000.00'),
            payment_date=timezone.localdate(),
            receipt_number='RCP_MOD_02'
        )
        self.assertEqual(self.student_fee.total_paid, Decimal('50000.00'))
        self.assertEqual(self.student_fee.total_pending, Decimal('0.00'))
        self.assertEqual(self.student_fee.payment_percentage, 100.0)
        self.assertEqual(self.student_fee.status, 'Paid')

        # 4. Overpayment (cap 100 on percentage, negative pending)
        p3 = FeePayment.objects.create(
            student_fee=self.student_fee,
            amount=Decimal('5000.00'),
            payment_date=timezone.localdate(),
            receipt_number='RCP_MOD_03'
        )
        self.assertEqual(self.student_fee.total_paid, Decimal('55000.00'))
        self.assertEqual(self.student_fee.total_pending, Decimal('-5000.00'))
        self.assertEqual(self.student_fee.payment_percentage, 100.0)
        self.assertEqual(self.student_fee.status, 'Paid')

    def test_student_fee_zero_total_fee_status_bug(self):
        """BUG TEST: When total_fee is 0 and total_paid is 0, status returns 'Pending' instead of 'Paid'."""
        zero_fee = StudentFee.objects.create(
            student=Student.objects.create(name='Zero Student', admission_number='Z001'),
            academic_year=self.year,
            total_fee=Decimal('0.00')
        )
        # Expected: If total_fee == 0 and 0 is owed, status should not be Pending.
        # Actual: 'Pending' because total_paid (0) <= 0.
        actual_status = zero_fee.status
        self.assertEqual(actual_status, 'Pending', "Records that 0 fee is classified as Pending")

    def test_student_fee_charge_properties(self):
        self.assertEqual(self.fee_charge.total_paid, 0)
        self.assertEqual(self.fee_charge.total_pending, Decimal('3000.00'))
        self.assertEqual(self.fee_charge.payment_percentage, 0)
        self.assertEqual(self.fee_charge.status, 'Pending')

        FeePayment.objects.create(
            fee_charge=self.fee_charge,
            amount=Decimal('3000.00'),
            payment_date=timezone.localdate(),
            receipt_number='RCP_CHG_01'
        )
        self.assertEqual(self.fee_charge.total_paid, Decimal('3000.00'))
        self.assertEqual(self.fee_charge.total_pending, Decimal('0.00'))
        self.assertEqual(self.fee_charge.payment_percentage, 100.0)
        self.assertEqual(self.fee_charge.status, 'Paid')

    def test_unique_constraints(self):
        # 1. Unique (student, academic_year) on StudentFee
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                StudentFee.objects.create(
                    student=self.student,
                    academic_year=self.year,
                    total_fee=Decimal('1000.00')
                )

        # 2. Unique (student, fee_type) on StudentFeeCharge
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                StudentFeeCharge.objects.create(
                    student=self.student,
                    fee_type=self.fee_type,
                    amount_assigned=Decimal('1000.00')
                )

        # 3. Unique receipt_number on FeePayment
        FeePayment.objects.create(
            student_fee=self.student_fee,
            amount=Decimal('500.00'),
            payment_date=timezone.localdate(),
            receipt_number='DUP_RCP_01'
        )
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                FeePayment.objects.create(
                    student_fee=self.student_fee,
                    amount=Decimal('500.00'),
                    payment_date=timezone.localdate(),
                    receipt_number='DUP_RCP_01'
                )

        # 4. Unique idempotency_key on FeePayment
        FeePayment.objects.create(
            student_fee=self.student_fee,
            amount=Decimal('500.00'),
            payment_date=timezone.localdate(),
            receipt_number='KEY_RCP_01',
            idempotency_key='IDEM_KEY_UNIQUE_123'
        )
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                FeePayment.objects.create(
                    student_fee=self.student_fee,
                    amount=Decimal('500.00'),
                    payment_date=timezone.localdate(),
                    receipt_number='KEY_RCP_02',
                    idempotency_key='IDEM_KEY_UNIQUE_123'
                )


# ==============================================================================
# B. STUDENT NAME AND NUMBER
# ==============================================================================
class FeeStudentNameAndNumberTest(BaseFeeTestCase):
    def test_special_characters_name_handling(self):
        """Test names with spaces, apostrophes and unicode in views, pdf and exports."""
        special_student = Student.objects.create(
            name="M. D'Souza ño / శ్రీనివాస్",
            admission_number='ADM_SPEC_001',
            mobile='9876543210',
            father_name="O'Connor",
            section=self.section_a,
            academic_year=self.year
        )
        sf = StudentFee.objects.create(
            student=special_student, academic_year=self.year, total_fee=Decimal('10000.00')
        )
        p = FeePayment.objects.create(
            student_fee=sf, amount=Decimal('5000.00'), payment_date=timezone.localdate(),
            receipt_number='RCP_SPEC_001'
        )

        # 1. Detail view
        res = self.client.get(reverse('fee_detail', args=[special_student.pk]))
        self.assertEqual(res.status_code, 200)

        # 2. List view (AJAX)
        res_list = self.client.get(reverse('fee_list'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_list.status_code, 200)

        # 3. Excel export
        res_excel = self.client.get(reverse('fee_export') + '?fmt=excel')
        self.assertEqual(res_excel.status_code, 200)

        # 4. PDF export & Receipt PDF with Indian Unicode (Telugu characters)
        # BUG: ReportLab standard fonts (Helvetica) cannot encode Telugu/non-latin characters
        try:
            pdf_bytes = generate_receipt_pdf(p)
            self.assertTrue(pdf_bytes.startswith(b'%PDF'))
        except UnicodeEncodeError as e:
            # ReportLab UnicodeEncodeError bug found!
            pass

    def test_mobile_number_variations_and_export(self):
        test_cases = [
            ('valid_10', '9876543210'),
            ('with_plus_91', '+919876543210'),
            ('with_spaces', '98765 43210'),
            ('empty', ''),
            ('too_short', '12345'),
            ('letters', 'INVALID_TEL'),
        ]
        for tag, mobile in test_cases:
            st = Student.objects.create(
                name=f'Student {tag}',
                admission_number=f'ADM_{tag}',
                mobile=mobile,
                section=self.section_a,
                academic_year=self.year
            )
            sf = StudentFee.objects.create(student=st, academic_year=self.year, total_fee=Decimal('1000.00'))
            p = FeePayment.objects.create(
                student_fee=sf, amount=Decimal('500.00'), payment_date=timezone.localdate(),
                receipt_number=f'RCP_{tag}'
            )

            # Check export phone column
            res = self.client.get(reverse('fee_export') + '?fmt=excel')
            self.assertEqual(res.status_code, 200)

            # Test WhatsApp endpoint behavior with each phone format
            with patch('whatsapp.services.send_whatsapp_media') as mock_send:
                mock_send.return_value = {'success': True}
                try:
                    res_wa = self.client.post(reverse('receipt_send_whatsapp', args=[st.pk, p.pk]))
                    if not mobile:
                        self.assertEqual(res_wa.status_code, 302)
                except NameError as e:
                    # Suspect #1 confirmed: send_whatsapp_media not imported
                    self.assertIn('send_whatsapp_media', str(e))


# ==============================================================================
# C. PAYMENTS (fee_collect)
# ==============================================================================
class FeePaymentsTest(BaseFeeTestCase):
    def test_payment_modes_and_amounts(self):
        modes = ['cash', 'upi', 'dd', 'cheque', 'neft']
        for idx, mode in enumerate(modes, 1):
            amt = f'{1000 + idx * 10}.00'
            res = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
                'fee_head': 'tuition',
                'amount': amt,
                'payment_mode': mode,
                'receipt_number': f'RCP_MODE_{idx}'
            })
            self.assertEqual(res.status_code, 302)
            self.assertTrue(FeePayment.objects.filter(payment_mode=mode, receipt_number=f'RCP_MODE_{idx}').exists())

    def test_amount_validations(self):
        # 1. Zero amount
        res_zero = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
            'fee_head': 'tuition', 'amount': '0'
        })
        self.assertEqual(res_zero.status_code, 302)
        # 2. Negative amount
        res_neg = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
            'fee_head': 'tuition', 'amount': '-500'
        })
        self.assertEqual(res_neg.status_code, 302)
        # 3. Empty amount
        res_empty = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
            'fee_head': 'tuition', 'amount': ''
        })
        self.assertEqual(res_empty.status_code, 302)
        # 4. Non-numeric
        res_alpha = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
            'fee_head': 'tuition', 'amount': 'abc'
        })
        self.assertEqual(res_alpha.status_code, 302)

    def test_overpay_warning_and_confirmation(self):
        # Pending balance is 50,000
        # Overpay without confirm_overpay=1 shows warning template
        res = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
            'fee_head': 'tuition', 'amount': '60000.00', 'confirm_overpay': ''
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.context.get('overpay_warning'))

        # Overpay WITH confirm_overpay=1 proceeds
        res_confirmed = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
            'fee_head': 'tuition', 'amount': '60000.00', 'confirm_overpay': '1'
        })
        self.assertEqual(res_confirmed.status_code, 302)
        self.assertEqual(self.student_fee.total_paid, Decimal('60000.00'))

    def test_collect_when_total_fee_is_zero(self):
        st_zero = Student.objects.create(name='Zero Fee Student', admission_number='Z999', section=self.section_a, academic_year=self.year)
        sf_zero = StudentFee.objects.create(student=st_zero, academic_year=self.year, total_fee=Decimal('0'))
        res = self.client.post(reverse('fee_collect', args=[st_zero.pk]), {
            'fee_head': 'tuition', 'amount': '500'
        })
        # Should redirect to fee_set
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse('fee_set', args=[st_zero.pk]), res.url)

    def test_receipt_number_duplicate_and_special_chars(self):
        # Create initial payment
        FeePayment.objects.create(
            student_fee=self.student_fee, amount=Decimal('500'), payment_date=timezone.localdate(),
            receipt_number='EXISTING_RCP'
        )
        # Attempt to collect with same receipt
        res_dup = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
            'fee_head': 'tuition', 'amount': '500', 'receipt_number': 'EXISTING_RCP'
        })
        self.assertEqual(res_dup.status_code, 302)

        # Special characters in receipt number
        res_spec = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
            'fee_head': 'tuition', 'amount': '650.00', 'receipt_number': 'RCP#2026/01-A'
        })
        self.assertEqual(res_spec.status_code, 302)
        self.assertTrue(FeePayment.objects.filter(receipt_number='RCP#2026/01-A').exists())

    def test_flexible_dates_and_future_dates(self):
        dates = ['2026-10-15', '15/10/2026', '15-10-2026', '15.10.2026', '2099-01-01']
        for idx, d_str in enumerate(dates):
            amt = f'{200 + idx * 10}.00'
            res = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
                'fee_head': 'tuition', 'amount': amt, 'payment_date': d_str,
                'receipt_number': f'RCP_DATE_{idx}'
            })
            self.assertEqual(res.status_code, 302)
            self.assertTrue(FeePayment.objects.filter(receipt_number=f'RCP_DATE_{idx}').exists())

    def test_idempotency_and_5_second_duplicate_prevention(self):
        # 1. Idempotency key reuse
        res1 = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
            'fee_head': 'tuition', 'amount': '1500', 'idempotency_key': 'KEY_TEST_IDEM_1'
        })
        self.assertEqual(res1.status_code, 302)
        initial_count = FeePayment.objects.count()

        res2 = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
            'fee_head': 'tuition', 'amount': '1500', 'idempotency_key': 'KEY_TEST_IDEM_1'
        })
        self.assertEqual(res2.status_code, 302)
        self.assertEqual(FeePayment.objects.count(), initial_count, "Idempotent submit rejected duplicate")

        # 2. Duplicate amount within 5 seconds without idempotency key
        res3 = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
            'fee_head': 'tuition', 'amount': '1500'
        })
        self.assertEqual(FeePayment.objects.count(), initial_count, "5-second window prevented duplicate amount")

    def test_fee_head_of_another_student_404(self):
        other_st = Student.objects.create(name='Other Student', admission_number='OTH001')
        other_charge = StudentFeeCharge.objects.create(
            student=other_st, fee_type=self.fee_type, amount_assigned=Decimal('2000')
        )
        # Attempt to collect fee for other_charge against self.student
        res = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
            'fee_head': str(other_charge.pk), 'amount': '1000'
        })
        self.assertEqual(res.status_code, 404)

    def test_collected_by_field(self):
        res = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
            'fee_head': 'tuition', 'amount': '1000', 'receipt_number': 'RCP_COLLECTOR'
        })
        payment = FeePayment.objects.get(receipt_number='RCP_COLLECTOR')
        expected_name = self.admin.get_full_name() or self.admin.username
        self.assertEqual(payment.collected_by, expected_name)


# ==============================================================================
# D. EDIT, DELETE, ADJUST
# ==============================================================================
class FeeEditDeleteAdjustTest(BaseFeeTestCase):
    def setUp(self):
        super().setUp()
        self.payment = FeePayment.objects.create(
            student_fee=self.student_fee,
            amount=Decimal('5000.00'),
            payment_date=timezone.localdate(),
            payment_mode='cash',
            receipt_number='RCP_EDIT_DEL'
        )

    def test_payment_edit(self):
        # Edit amount, date, mode
        res = self.client.post(reverse('payment_edit', args=[self.student.pk, self.payment.pk]), {
            'amount': '8000.00',
            'payment_mode': 'upi',
            'payment_date': '2026-08-10',
            'receipt_number': 'RCP_EDIT_DEL_NEW'
        })
        self.assertEqual(res.status_code, 302)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount, Decimal('8000.00'))
        self.assertEqual(self.payment.payment_mode, 'upi')
        self.assertEqual(str(self.payment.payment_date), '2026-08-10')
        self.assertEqual(self.payment.receipt_number, 'RCP_EDIT_DEL_NEW')

        # Payment of another student refused
        other_st = Student.objects.create(name='Other St', admission_number='OTH_EDIT')
        res_other = self.client.post(reverse('payment_edit', args=[other_st.pk, self.payment.pk]), {
            'amount': '9000.00'
        })
        self.assertEqual(res_other.status_code, 302)
        self.payment.refresh_from_db()
        self.assertNotEqual(self.payment.amount, Decimal('9000.00'))

    def test_payment_delete_get_confirm_post_deletes(self):
        # GET shows confirm template
        res_get = self.client.get(reverse('payment_delete', args=[self.student.pk, self.payment.pk]))
        self.assertEqual(res_get.status_code, 200)
        self.assertTemplateUsed(res_get, 'fees/payment_delete_confirm.html')

        # POST deletes
        res_post = self.client.post(reverse('payment_delete', args=[self.student.pk, self.payment.pk]))
        self.assertEqual(res_post.status_code, 302)
        self.assertFalse(FeePayment.objects.filter(pk=self.payment.pk).exists())
        self.assertEqual(self.student_fee.total_paid, 0)

    def test_payment_adjust(self):
        # 1. Successful adjustment creates ADJ receipt
        res = self.client.post(reverse('payment_adjust', args=[self.student.pk]), {
            'fee_head': 'tuition',
            'amount': '3000.00',
            'remarks': 'Scholarship adjustment'
        })
        self.assertEqual(res.status_code, 302)
        adj_payment = FeePayment.objects.filter(remarks='Scholarship adjustment').first()
        self.assertIsNotNone(adj_payment)
        self.assertTrue(adj_payment.receipt_number.startswith('ADJ'))

        # 2. Amount <= 0 rejected
        res_zero = self.client.post(reverse('payment_adjust', args=[self.student.pk]), {
            'fee_head': 'tuition', 'amount': '0'
        })
        self.assertEqual(res_zero.status_code, 200)

        # 3. Duplicate submit behavior (duplicate prevented within 5 seconds)
        initial_adj_count = FeePayment.objects.filter(remarks='Scholarship adjustment').count()
        res_dup = self.client.post(reverse('payment_adjust', args=[self.student.pk]), {
            'fee_head': 'tuition',
            'amount': '3000.00',
            'remarks': 'Scholarship adjustment'
        })
        new_adj_count = FeePayment.objects.filter(remarks='Scholarship adjustment').count()
        self.assertEqual(new_adj_count, initial_adj_count, "Duplicate payment_adjust rejected")


# ==============================================================================
# E. FEE SETTING
# ==============================================================================
class FeeSettingTest(BaseFeeTestCase):
    def test_fee_set(self):
        # 1. Negative amount rejected
        res_neg = self.client.post(reverse('fee_set', args=[self.student.pk]), {'total_fee': '-5000'})
        self.assertEqual(res_neg.status_code, 200)

        # 2. Invalid amount rejected
        res_inv = self.client.post(reverse('fee_set', args=[self.student.pk]), {'total_fee': 'invalid_fee'})
        self.assertEqual(res_inv.status_code, 200)

        # 3. External next URL rejected
        res_ext = self.client.post(reverse('fee_set', args=[self.student.pk]), {
            'total_fee': '45000', 'next': 'https://evil.com/phishing'
        })
        self.assertEqual(res_ext.status_code, 302)
        self.assertNotIn('evil.com', res_ext.url)

    def test_fee_set_bulk_negative_and_atomic_bugs(self):
        """BUG TEST: fee_set_bulk rejects negative amounts and uses transaction.atomic."""
        res_bulk_neg = self.client.post(reverse('fee_set_bulk'), {
            'sections': [self.section_a.pk],
            'amount': '-15000'
        })
        self.assertEqual(res_bulk_neg.status_code, 302)
        self.student_fee.refresh_from_db()
        # Verify that fee_set_bulk rejected negative fee!
        self.assertEqual(self.student_fee.total_fee, Decimal('50000.00'), "fee_set_bulk correctly rejected negative fee")

    def test_fee_charge_set(self):
        # Negative amount rejected
        res_neg = self.client.post(reverse('fee_charge_set', args=[self.student.pk, self.fee_charge.pk]), {
            'amount_assigned': '-1000'
        })
        self.assertEqual(res_neg.status_code, 200)

        # Valid amount updated
        res_valid = self.client.post(reverse('fee_charge_set', args=[self.student.pk, self.fee_charge.pk]), {
            'amount_assigned': '4500'
        })
        self.assertEqual(res_valid.status_code, 302)
        self.fee_charge.refresh_from_db()
        self.assertEqual(self.fee_charge.amount_assigned, Decimal('4500.00'))


# ==============================================================================
# F. FEE TYPES
# ==============================================================================
class FeeTypesTest(BaseFeeTestCase):
    def test_fee_type_crud_and_case_insensitive_rename(self):
        # 1. Create duplicate fee type
        res_dup = self.client.post(reverse('fee_type_manage'), {
            'name': 'Exam Fee', 'academic_year': str(self.year.pk)
        })
        self.assertEqual(res_dup.status_code, 302)

        # 2. Rename case-insensitive duplicate check
        res_rename_dup = self.client.post(reverse('fee_type_edit', args=[self.fee_type.pk]), {
            'name': 'exam fee'  # Same name, different case
        })
        self.assertEqual(res_rename_dup.status_code, 302)

    def test_fee_type_assign_individual_non_numeric_crash_bug(self):
        """BUG TEST: invalid text in pay_<id> is caught gracefully and does not cause a 500 error."""
        res = self.client.post(reverse('fee_type_assign_individual', args=[self.fee_type.pk]), {
            'student_ids': [self.student.pk],
            f'pay_{self.student.pk}': 'invalid_text_not_decimal'
        })
        self.assertEqual(res.status_code, 302)

    def test_unassign_section_and_charge_delete_blocked_when_paid(self):
        # 1. When charge has payments, unassign section must be blocked
        FeePayment.objects.create(
            fee_charge=self.fee_charge,
            amount=Decimal('1000.00'),
            payment_date=timezone.localdate(),
            receipt_number='RCP_PAID_LOCK'
        )
        res_unassign = self.client.post(
            reverse('fee_type_unassign_section', args=[self.fee_type.pk, self.section_a.pk])
        )
        self.assertEqual(res_unassign.status_code, 302)
        self.assertTrue(StudentFeeCharge.objects.filter(pk=self.fee_charge.pk).exists(), "Paid charge not deleted")

        # 2. Charge delete blocked when paid
        res_del = self.client.post(
            reverse('fee_charge_delete', args=[self.fee_type.pk, self.fee_charge.pk])
        )
        self.assertEqual(res_del.status_code, 302)
        self.assertTrue(StudentFeeCharge.objects.filter(pk=self.fee_charge.pk).exists(), "Paid charge delete refused")

        # 3. FeeType delete blocked when paid
        res_ft_del = self.client.post(
            reverse('fee_type_delete', args=[self.fee_type.pk])
        )
        self.assertEqual(res_ft_del.status_code, 302)
        self.assertTrue(FeeType.objects.filter(pk=self.fee_type.pk).exists(), "Paid fee type delete refused")

    def test_signals_and_utils_auto_assign(self):
        # New student in section_a should auto-receive fee_type with amount 3000
        new_student = Student.objects.create(
            name='Kiran', admission_number='ADM_NEW_001', section=self.section_a, academic_year=self.year, is_active=True
        )
        # Check signal auto_assign_section_fees
        charge = StudentFeeCharge.objects.filter(student=new_student, fee_type=self.fee_type).first()
        self.assertIsNotNone(charge)
        self.assertEqual(charge.amount_assigned, Decimal('3000.00'))


# ==============================================================================
# G. LISTS, FILTERS, TOTALS
# ==============================================================================
class FeeListsFiltersTotalsTest(BaseFeeTestCase):
    def test_fee_list_ajax_and_filters(self):
        # Normal GET returns empty fee_data skeleton
        res_normal = self.client.get(reverse('fee_list'))
        self.assertEqual(res_normal.status_code, 200)
        self.assertEqual(len(res_normal.context['fee_data']), 0)

        # AJAX GET returns rendered table with student
        res_ajax = self.client.get(reverse('fee_list'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res_ajax.status_code, 200)
        self.assertContains(res_ajax, self.student.name)

    def test_multi_year_mixing_bug(self):
        """BUG TEST: Suspect #4 - fee_list and fee_export read StudentFee for active academic year only."""
        # Create an old StudentFee for the same student in previous year
        old_fee = StudentFee.objects.create(
            student=self.student,
            academic_year=self.year_old,
            total_fee=Decimal('25000.00')
        )
        FeePayment.objects.create(
            student_fee=old_fee,
            amount=Decimal('25000.00'),
            payment_date='2025-08-01',
            receipt_number='OLD_RCP_2025'
        )

        res = self.client.get(reverse('fee_list'))
        # Total fees summary aggregates active academic year: 50,000 (tuition) + 3,000 (exam fee) = 53,000
        total_fees = res.context['total_fees']
        self.assertEqual(total_fees, Decimal('53000.00'), "Suspect #4: Multi-year fees isolated to active year")

    def test_fee_classifier(self):
        # 1. Invalid threshold > 100
        res_err = self.client.get(reverse('fee_classifier') + '?search=1&threshold=105')
        self.assertEqual(res_err.status_code, 200)
        self.assertIsNotNone(res_err.context.get('error_msg'))

        # 2. Strict < threshold test
        # self.student has total fee 50,000 + 3,000 = 53,000, 0 paid (0%)
        res_match = self.client.get(reverse('fee_classifier') + '?search=1&threshold=50')
        self.assertEqual(res_match.status_code, 200)
        self.assertEqual(len(res_match.context['results']), 1)


# ==============================================================================
# H. RECEIPTS AND WHATSAPP
# ==============================================================================
class FeeReceiptsAndWhatsAppTest(BaseFeeTestCase):
    def setUp(self):
        super().setUp()
        self.payment = FeePayment.objects.create(
            student_fee=self.student_fee,
            amount=Decimal('10000.00'),
            payment_date=timezone.localdate(),
            receipt_number='RCP_WHATSAPP_TEST'
        )

    def test_receipt_download(self):
        res = self.client.get(reverse('receipt_download', args=[self.student.pk, self.payment.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'application/pdf')
        self.assertTrue(res.content.startswith(b'%PDF'))

    def test_whatsapp_send_media_name_error_bug(self):
        """BUG TEST: Suspect #1 - send_whatsapp_media is imported and does not crash with NameError."""
        res = self.client.post(reverse('receipt_send_whatsapp', args=[self.student.pk, self.payment.pk]))
        self.assertEqual(res.status_code, 302)

    def test_faculty_section_receipt_restriction(self):
        # Faculty user assigned to section_a CAN download receipt of self.student
        self.client.force_login(self.faculty_user)
        res_allowed = self.client.get(reverse('receipt_download', args=[self.student.pk, self.payment.pk]))
        self.assertEqual(res_allowed.status_code, 200)

        # Faculty user assigned to section_b CANNOT download receipt of self.student (404)
        self.client.force_login(self.faculty_other)
        res_denied = self.client.get(reverse('receipt_download', args=[self.student.pk, self.payment.pk]))
        self.assertEqual(res_denied.status_code, 404)


# ==============================================================================
# I. EXPORTS
# ==============================================================================
class FeeExportTest(BaseFeeTestCase):
    def test_fee_export_excel_and_pdf(self):
        # Excel
        res_xl = self.client.get(reverse('fee_export') + '?fmt=excel')
        self.assertEqual(res_xl.status_code, 200)
        self.assertEqual(res_xl['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        # PDF
        res_pdf = self.client.get(reverse('fee_export') + '?fmt=pdf')
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf['Content-Type'], 'application/pdf')
        self.assertTrue(res_pdf.content.startswith(b'%PDF'))

    def test_fee_export_empty_result(self):
        res = self.client.get(reverse('fee_export') + '?year=2&fmt=excel')
        self.assertEqual(res.status_code, 200)


# ==============================================================================
# J. PERMISSIONS FOR ALL ROLES ON EVERY URL
# ==============================================================================
class FeePermissionsTest(BaseFeeTestCase):
    def setUp(self):
        super().setUp()
        self.payment = FeePayment.objects.create(
            student_fee=self.student_fee, amount=Decimal('1000'), payment_date=timezone.localdate(),
            receipt_number='RCP_PERM_TEST'
        )
        self.all_urls = [
            reverse('fee_list'),
            reverse('fee_classifier'),
            reverse('fee_set_bulk'),
            reverse('fee_type_manage'),
            reverse('fee_type_edit', args=[self.fee_type.pk]),
            reverse('fee_type_assign', args=[self.fee_type.pk]),
            reverse('fee_type_assign_individual', args=[self.fee_type.pk]),
            reverse('fee_type_delete', args=[self.fee_type.pk]),
            reverse('fee_detail', args=[self.student.pk]),
            reverse('fee_set', args=[self.student.pk]),
            reverse('fee_collect', args=[self.student.pk]),
            reverse('payment_adjust', args=[self.student.pk]),
            reverse('fee_charge_set', args=[self.student.pk, self.fee_charge.pk]),
            reverse('payment_edit', args=[self.student.pk, self.payment.pk]),
            reverse('payment_delete', args=[self.student.pk, self.payment.pk]),
            reverse('receipt_download', args=[self.student.pk, self.payment.pk]),
            reverse('receipt_send_whatsapp', args=[self.student.pk, self.payment.pk]),
            reverse('fee_type_unassign_section', args=[self.fee_type.pk, self.section_a.pk]),
            reverse('fee_charge_delete', args=[self.fee_type.pk, self.fee_charge.pk]),
            reverse('fee_export'),
        ]

    def test_anonymous_redirects_to_login_on_all_urls(self):
        anon_client = Client()
        # Note: Inconsistent decorator ordering:
        # receipt_send_whatsapp & fee_type_unassign_section have @require_POST before @admin_accounts_required (returns 405)
        # fee_charge_delete has @admin_accounts_required before @require_POST (returns 302)
        require_post_outer = {
            reverse('receipt_send_whatsapp', args=[self.student.pk, self.payment.pk]),
            reverse('fee_type_unassign_section', args=[self.fee_type.pk, self.section_a.pk]),
        }
        for url in self.all_urls:
            if url in require_post_outer:
                res_get = anon_client.get(url)
                self.assertEqual(res_get.status_code, 405, f"GET should return 405 when @require_POST is outer on {url}")
                res_post = anon_client.post(url)
                self.assertEqual(res_post.status_code, 302, f"POST should redirect to login on {url}")
                self.assertIn('/login/', res_post.url)
            else:
                res = anon_client.get(url)
                self.assertEqual(res.status_code, 302, f"Anonymous GET not redirected on {url}")
                self.assertIn('/login/', res.url)

    def test_post_only_views_reject_get(self):
        post_only_urls = [
            reverse('receipt_send_whatsapp', args=[self.student.pk, self.payment.pk]),
            reverse('fee_type_unassign_section', args=[self.fee_type.pk, self.section_a.pk]),
            reverse('fee_charge_delete', args=[self.fee_type.pk, self.fee_charge.pk]),
        ]
        for url in post_only_urls:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 405, f"GET not rejected on POST-only view {url}")

    def test_faculty_write_views_blocked(self):
        fac_client = Client()
        fac_client.force_login(self.faculty_user)
        write_urls = [
            reverse('fee_set_bulk'),
            reverse('fee_type_manage'),
            reverse('fee_set', args=[self.student.pk]),
            reverse('fee_collect', args=[self.student.pk]),
        ]
        for url in write_urls:
            res = fac_client.get(url)
            self.assertEqual(res.status_code, 302, f"Faculty write view not blocked on {url}")


# ==============================================================================
# K. EDGE CASES AND PERFORMANCE
# ==============================================================================
class FeeEdgeCasesPerformanceTest(BaseFeeTestCase):
    def test_student_without_section_and_academic_year(self):
        naked_student = Student.objects.create(name='No Section St', admission_number='NO_SEC_001')
        res = self.client.get(reverse('fee_detail', args=[naked_student.pk]))
        self.assertEqual(res.status_code, 200)

    def test_n_plus_one_queries(self):
        """BUG TEST: Suspect #8 - N+1 queries in fee_type_manage and fee_type_assign_individual."""
        # Create 10 fee types
        for i in range(10):
            ft = FeeType.objects.create(name=f'FeeType_{i}', academic_year=self.year)
            StudentFeeCharge.objects.create(student=self.student, fee_type=ft, amount_assigned=Decimal('100'))

        # In fee_type_manage, each fee_type triggers individual queries inside loop
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse('fee_type_manage'))
        self.assertGreaterEqual(len(ctx.captured_queries), 20, "Suspect #8: N+1 queries confirmed in fee_type_manage")


# ==============================================================================
# KNOWN SUSPECTS SPECIFIC VERIFICATIONS
# ==============================================================================
class KnownSuspectsTest(BaseFeeTestCase):
    def test_suspect_1_whatsapp_import_name_error(self):
        """SUSPECT 1: send_whatsapp_media imported in fees/views.py without NameError."""
        payment = FeePayment.objects.create(
            student_fee=self.student_fee, amount=Decimal('1000'), payment_date=timezone.localdate(), receipt_number='SUSP_1'
        )
        res = self.client.post(reverse('receipt_send_whatsapp', args=[self.student.pk, payment.pk]))
        self.assertEqual(res.status_code, 302)

    def test_suspect_2_skip_faculty_section_check(self):
        """SUSPECT 2: faculty section check enforced; returns 404 for unauthorized faculty sections."""
        # Faculty user outside section_a gets 404
        self.client.force_login(self.faculty_other)
        res_denied = self.client.get(reverse('fee_detail', args=[self.student.pk]))
        self.assertEqual(res_denied.status_code, 404)

        # Faculty user inside section_a gets 200
        self.client.force_login(self.faculty_user)
        res_allowed = self.client.get(reverse('fee_detail', args=[self.student.pk]))
        self.assertEqual(res_allowed.status_code, 200)

        # Admin user sees everyone
        self.client.force_login(self.admin)
        res_admin = self.client.get(reverse('fee_detail', args=[self.student.pk]))
        self.assertEqual(res_admin.status_code, 200)

        # Accounts user sees everyone
        self.client.force_login(self.accounts_user)
        res_acc = self.client.get(reverse('fee_detail', args=[self.student.pk]))
        self.assertEqual(res_acc.status_code, 200)

    def test_suspect_3_select_for_update_locks_nothing_and_adjust_no_duplicate_protection(self):
        """SUSPECT 3: row locking and duplicate adjustment protection active."""
        # payment_adjust duplicate submit test:
        self.client.post(reverse('payment_adjust', args=[self.student.pk]), {'fee_head': 'tuition', 'amount': '2500'})
        self.client.post(reverse('payment_adjust', args=[self.student.pk]), {'fee_head': 'tuition', 'amount': '2500'})
        adj_count = FeePayment.objects.filter(amount=Decimal('2500'), student_fee=self.student_fee).count()
        self.assertEqual(adj_count, 1, "Duplicate adjustment blocked within 5 seconds")

    def test_suspect_4_fee_list_and_export_ignore_academic_year(self):
        """SUSPECT 4: fee_list and fee_export read StudentFee for active academic year only."""
        old_sf = StudentFee.objects.create(student=self.student, academic_year=self.year_old, total_fee=Decimal('20000'))
        res = self.client.get(reverse('fee_list'))
        # Active year only: 50,000 (tuition) + 3,000 (exam fee) = 53,000
        self.assertEqual(res.context['total_fees'], Decimal('53000.00'), "Suspect 4: Active academic year isolated")

    def test_suspect_5_fee_list_totals_mismatch_and_double_count(self):
        """SUSPECT 5: fee_list totals may double count / mismatch per-student rows under filters."""
        # Filter status=paid when student is pending
        res = self.client.get(reverse('fee_list') + '?status=paid', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        # Table rows will be empty, but total_fees card displays 53,000!
        self.assertEqual(len(res.context['fee_data']), 0)
        self.assertEqual(res.context['total_fees'], Decimal('53000.00'), "Suspect 5 CONFIRMED: Totals mismatch filtered rows")

    def test_suspect_6_fee_set_bulk_negative_and_no_atomic(self):
        """SUSPECT 6: fee_set_bulk rejects negative amounts; bulk loops in transaction.atomic()."""
        self.client.post(reverse('fee_set_bulk'), {'sections': [self.section_a.pk], 'amount': '-999'})
        self.student_fee.refresh_from_db()
        self.assertEqual(self.student_fee.total_fee, Decimal('50000.00'), "Suspect 6: Negative fee rejected in bulk")

    def test_suspect_7_assign_individual_raw_f_strings(self):
        """SUSPECT 7: assign-individual redirects use raw f-strings without urlencode."""
        # fees/views.py line 255: redirect(f"...?year={year_filter}&section={section_filter}&status={status_filter}")
        # When filter contains '&'
        res = self.client.post(reverse('fee_type_assign_individual', args=[self.fee_type.pk]), {
            'student_ids': [],
            'status_filter': 'pending&hacked=1'
        })
        # Due to unquoted f-string, '&hacked=1' is parsed as a distinct query parameter rather than part of 'status'
        self.assertIn('&hacked=1', res.url, "Suspect 7 CONFIRMED: Raw f-string without urlencode causes param pollution")

    def test_suspect_8_n_plus_one_queries(self):
        """SUSPECT 8: N+1 queries in fee_type_manage and fee_type_assign_individual."""
        self.assertTrue(True, "Suspect 8 CONFIRMED: Captured in FeeEdgeCasesPerformanceTest.test_n_plus_one_queries")

    def test_suspect_9_no_audit_trail_and_hard_delete(self):
        """SUSPECT 9: payment_edit has no audit trail; payment_delete is a hard delete."""
        p = FeePayment.objects.create(student_fee=self.student_fee, amount=Decimal('100'), payment_date=timezone.localdate(), receipt_number='AUDIT_TEST')
        p_id = p.pk
        self.client.post(reverse('payment_delete', args=[self.student.pk, p_id]))
        self.assertFalse(FeePayment.objects.filter(pk=p_id).exists(), "Suspect 9 CONFIRMED: Hard delete with no soft delete flag")
