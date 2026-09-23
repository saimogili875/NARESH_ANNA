from django.db import models
from students.models import Student
from accounts.models import AcademicYear


class StudentFee(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='fees')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    total_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'academic_year']

    @property
    def total_paid(self):
        return sum(p.amount for p in self.payments.all())

    @property
    def total_pending(self):
        return self.total_fee - self.total_paid

    @property
    def payment_percentage(self):
        if self.total_fee == 0:
            return 0
        pct = (self.total_paid / self.total_fee) * 100
        return round(min(pct, 100), 1)

    @property
    def status(self):
        if self.total_paid <= 0:
            return 'Pending'
        elif self.total_paid >= self.total_fee:
            return 'Paid'
        return 'Partial'

    def __str__(self):
        return f"{self.student.name} - {self.academic_year} - ₹{self.total_fee}"


class FeePayment(models.Model):
    PAYMENT_MODES = [
        ('cash', 'Cash'),
        ('upi', 'UPI'),
        ('dd', 'Demand Draft'),
        ('cheque', 'Cheque'),
        ('neft', 'NEFT/RTGS'),
    ]

    student_fee = models.ForeignKey(StudentFee, on_delete=models.CASCADE, null=True, blank=True, related_name='payments')
    fee_charge = models.ForeignKey('StudentFeeCharge', on_delete=models.CASCADE, null=True, blank=True, related_name='payments')
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()           # Admin/Accounts can set this manually
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODES, default='cash')
    receipt_number = models.CharField(max_length=30, unique=True)   # Admin can set custom
    collected_by = models.CharField(max_length=100, blank=True)
    remarks = models.CharField(max_length=200, blank=True)
    idempotency_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        if self.student_fee:
            return f"Receipt #{self.receipt_number} - {self.student_fee.student.name} (Tuition) - ₹{self.amount}"
        if self.fee_charge:
            return f"Receipt #{self.receipt_number} - {self.fee_charge.student.name} ({self.fee_charge.fee_type.name}) - ₹{self.amount}"
        return f"Receipt #{self.receipt_number} - Unknown - ₹{self.amount}"


class FeeType(models.Model):
    name = models.CharField(max_length=100)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['name', 'academic_year']

    def __str__(self):
        return f"{self.name} ({self.academic_year})"


class StudentFeeCharge(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='other_fees')
    fee_type = models.ForeignKey(FeeType, on_delete=models.CASCADE, related_name='charges')
    amount_assigned = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['student', 'fee_type']

    @property
    def total_paid(self):
        return sum(p.amount for p in self.payments.all())

    @property
    def total_pending(self):
        return self.amount_assigned - self.total_paid

    @property
    def payment_percentage(self):
        if self.amount_assigned == 0:
            return 0
        pct = (self.total_paid / self.amount_assigned) * 100
        return round(min(pct, 100), 1)

    @property
    def status(self):
        if self.total_paid <= 0:
            return 'Pending'
        elif self.total_paid >= self.amount_assigned:
            return 'Paid'
        return 'Partial'

    def __str__(self):
        return f"{self.student.name} - {self.fee_type.name} - ₹{self.amount_assigned}"
