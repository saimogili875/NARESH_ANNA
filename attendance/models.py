from django.db import models
from students.models import Student
from accounts.models import Section


class Attendance(models.Model):
    STATUS_PRESENT = 'P'
    STATUS_ABSENT = 'A'
    STATUS_CHOICES = [
        (STATUS_PRESENT, 'Present'),
        (STATUS_ABSENT, 'Absent'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField()
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default=STATUS_PRESENT)
    section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True)
    remarks = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ['student', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"{self.student.name} - {self.date} - {self.status}"
