from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from accounts.models import User, AcademicYear, Group, Section
from students.models import Student
from fees.models import StudentFee, FeePayment, FeeType, StudentFeeCharge


class FeeManagementFeaturesTest(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            name='2026-2027', start_date='2026-06-01', end_date='2027-05-31', is_active=True
        )
        self.admin = User.objects.create_user(username='admin_user', password='password123', role='admin')
        self.group, _ = Group.objects.get_or_create(code='MPC', defaults={'name': 'MPC', 'academic_year': self.year})
        self.section, _ = Section.objects.get_or_create(group=self.group, year='1', name='A', defaults={'academic_year': self.year})
        self.student = Student.objects.create(
            name='Test Student',
            admission_number='2026001',
            section=self.section,
            academic_year=self.year
        )
        self.client = Client()
        self.client.force_login(self.admin)

    def test_fee_set_and_adjustment(self):
        # Set total tuition fee
        response = self.client.post(reverse('fee_set', args=[self.student.pk]), {'total_fee': '50000'})
        self.assertEqual(response.status_code, 302)
        sf = StudentFee.objects.get(student=self.student, academic_year=self.year)
        self.assertEqual(sf.total_fee, 50000)

        # Collect initial payment
        response = self.client.post(reverse('fee_collect', args=[self.student.pk]), {
            'fee_head': 'tuition',
            'amount': '10000',
            'payment_mode': 'cash',
            'remarks': 'First installment'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(sf.total_paid, 10000)
        self.assertEqual(sf.total_pending, 40000)

        # Edit payment
        payment = sf.payments.first()
        response = self.client.post(reverse('payment_edit', args=[self.student.pk, payment.pk]), {
            'amount': '15000',
            'payment_mode': 'upi',
            'receipt_number': 'RCPNEW123',
            'remarks': 'Corrected payment amount'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(sf.total_paid, 15000)
        payment.refresh_from_db()
        self.assertEqual(payment.receipt_number, 'RCPNEW123')

        # Test duplicate receipt number check
        payment2 = FeePayment.objects.create(student_fee=sf, amount=1000, payment_date=timezone.localdate(), receipt_number='RCPOTHER999')
        res_dup = self.client.post(reverse('payment_edit', args=[self.student.pk, payment2.pk]), {
            'amount': '1000',
            'payment_mode': 'cash',
            'receipt_number': 'RCPNEW123'
        })
        self.assertEqual(res_dup.status_code, 302)
        payment2.refresh_from_db()
        self.assertEqual(payment2.receipt_number, 'RCPOTHER999')
        payment2.delete()

        # Add payment adjustment
        response = self.client.post(reverse('payment_adjust', args=[self.student.pk]), {
            'fee_head': 'tuition',
            'amount': '5000',
            'remarks': 'Manual correction by admin'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(sf.total_paid, 20000)

        # Delete payment
        response = self.client.post(reverse('payment_delete', args=[self.student.pk, payment.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(sf.total_paid, 5000)

    def test_fee_type_assign_individual_and_partial_payment(self):
        fee_type = FeeType.objects.create(name='Bus Fee', academic_year=self.year)
        response = self.client.post(reverse('fee_type_assign_individual', args=[fee_type.pk]), {
            'student_ids': [self.student.pk],
            f'amount_{self.student.pk}': '6000',
            f'pay_{self.student.pk}': '2000'
        })
        self.assertEqual(response.status_code, 302)

        charge = StudentFeeCharge.objects.get(student=self.student, fee_type=fee_type)
        self.assertEqual(charge.amount_assigned, 6000)
        self.assertEqual(charge.total_paid, 2000)
        self.assertEqual(charge.total_pending, 4000)
        self.assertEqual(charge.status, 'Partial')

    def test_hide_fully_paid_fees_in_collect_and_list(self):
        sf = StudentFee.objects.create(student=self.student, academic_year=self.year, total_fee=10000)
        FeePayment.objects.create(student_fee=sf, amount=10000, payment_date=timezone.localdate(), receipt_number='RCPTEST1')

        fee_type = FeeType.objects.create(name='Lab Fee', academic_year=self.year)
        charge = StudentFeeCharge.objects.create(student=self.student, fee_type=fee_type, amount_assigned=3000)

        # Check fee_collect hides fully paid tuition
        response = self.client.get(reverse('fee_collect', args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Lab Fee')

        # Check fee_list pending status filter
        response = self.client.get(reverse('fee_list') + '?status=pending')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student.name)

        # Pay off Lab Fee fully
        FeePayment.objects.create(fee_charge=charge, amount=3000, payment_date=timezone.localdate(), receipt_number='RCPTEST2')

        # Now all fees are paid - student should be hidden from default pending list
        response = self.client.get(reverse('fee_list') + '?status=pending')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.student.name)

        # But student should still show up when filtering status=paid or status=all
        response = self.client.get(reverse('fee_list') + '?status=paid')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student.name)

    def test_receipt_pdf_generation(self):
        sf = StudentFee.objects.create(student=self.student, academic_year=self.year, total_fee=10000)
        p1 = FeePayment.objects.create(student_fee=sf, amount=5000, payment_date=timezone.localdate(), receipt_number='RCP1001')
        
        fee_type = FeeType.objects.create(name='Books Fee', academic_year=self.year)
        charge = StudentFeeCharge.objects.create(student=self.student, fee_type=fee_type, amount_assigned=2000)
        p2 = FeePayment.objects.create(fee_charge=charge, amount=2000, payment_date=timezone.localdate(), receipt_number='RCP1002')

        res1 = self.client.get(reverse('receipt_download', args=[self.student.pk, p1.pk]))
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1['Content-Type'], 'application/pdf')

        res2 = self.client.get(reverse('receipt_download', args=[self.student.pk, p2.pk]))
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2['Content-Type'], 'application/pdf')

    def test_section_assignment_indication_and_unassign(self):
        fee_type = FeeType.objects.create(name='Hostel Fee', academic_year=self.year)
        StudentFeeCharge.objects.create(student=self.student, fee_type=fee_type, amount_assigned=15000)

        # Check assign_type GET includes is_assigned=True and assigned_amount
        res = self.client.get(reverse('fee_type_assign', args=[fee_type.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Already assigned ₹15000')

        # Test unassigning section
        res_unassign = self.client.post(reverse('fee_type_unassign_section', args=[fee_type.pk, self.section.pk]))
        self.assertEqual(res_unassign.status_code, 302)
        self.assertFalse(StudentFeeCharge.objects.filter(student=self.student, fee_type=fee_type).exists())

    def test_individual_charge_delete(self):
        fee_type = FeeType.objects.create(name='Uniform Fee', academic_year=self.year)
        charge = StudentFeeCharge.objects.create(student=self.student, fee_type=fee_type, amount_assigned=2500)

        res_delete = self.client.get(reverse('fee_charge_delete', args=[fee_type.pk, charge.pk]))
        self.assertEqual(res_delete.status_code, 302)
        self.assertFalse(StudentFeeCharge.objects.filter(pk=charge.pk).exists())

    def test_assign_individual_status_filter_and_switcher(self):
        ft1 = FeeType.objects.create(name='Exam Fee', academic_year=self.year)
        c1 = StudentFeeCharge.objects.create(student=self.student, fee_type=ft1, amount_assigned=1000)

        res_all = self.client.get(reverse('fee_type_assign_individual', args=[ft1.pk]))
        self.assertEqual(res_all.status_code, 200)
        self.assertContains(res_all, self.student.name)
        self.assertContains(res_all, 'Exam Fee')

        res_pending = self.client.get(reverse('fee_type_assign_individual', args=[ft1.pk]) + '?status=pending')
        self.assertEqual(res_pending.status_code, 200)
        self.assertContains(res_pending, self.student.name)

        res_paid = self.client.get(reverse('fee_type_assign_individual', args=[ft1.pk]) + '?status=paid')
        self.assertEqual(res_paid.status_code, 200)
        self.assertNotContains(res_paid, self.student.name)

    def test_fee_type_edit(self):
        ft = FeeType.objects.create(name='Old Fee Name', academic_year=self.year)
        res = self.client.post(reverse('fee_type_edit', args=[ft.pk]), {'name': 'New Fee Name'})
        self.assertEqual(res.status_code, 302)
        ft.refresh_from_db()
        self.assertEqual(ft.name, 'New Fee Name')

    def test_fee_list_specific_fee_type_filter(self):
        sf = StudentFee.objects.create(student=self.student, academic_year=self.year, total_fee=5000)
        ft_books = FeeType.objects.create(name='Books Fee', academic_year=self.year)
        charge_books = StudentFeeCharge.objects.create(student=self.student, fee_type=ft_books, amount_assigned=2000)

        # Filter by Books Fee + status=pending -> Should contain student
        res1 = self.client.get(reverse('fee_list') + f'?fee_type={ft_books.id}&status=pending')
        self.assertEqual(res1.status_code, 200)
        self.assertContains(res1, self.student.name)

        # Pay off Books Fee fully
        FeePayment.objects.create(fee_charge=charge_books, amount=2000, payment_date=timezone.localdate(), receipt_number='RCPBK001')

    def test_fee_export_with_section_and_fee_type_filters(self):
        sf = StudentFee.objects.create(student=self.student, academic_year=self.year, total_fee=8000)
        
        # Test PDF export with section filter
        res_pdf = self.client.get(reverse('fee_export') + f'?fmt=pdf&section={self.section.id}&status=pending')
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf['Content-Type'], 'application/pdf')

        # Test Excel export with section filter
        res_excel = self.client.get(reverse('fee_export') + f'?fmt=excel&section={self.section.id}&status=pending')
        self.assertEqual(res_excel.status_code, 200)
        self.assertEqual(res_excel['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    def test_auto_assign_section_fees_signal(self):
        ft = FeeType.objects.create(name='Library Fee', academic_year=self.year)
        StudentFeeCharge.objects.create(student=self.student, fee_type=ft, amount_assigned=1500)

        # Create new student in same section
        new_student = Student.objects.create(
            name='New Student',
            admission_number='2026099',
            section=self.section,
            academic_year=self.year
        )

        charge = StudentFeeCharge.objects.filter(student=new_student, fee_type=ft).first()
        self.assertIsNotNone(charge)
        self.assertEqual(charge.amount_assigned, 1500)




