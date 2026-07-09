from django.db import models
from accounts.models import User


class Faculty(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='faculty_profile')
    employee_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    subject = models.CharField(max_length=50)
    phone = models.CharField(max_length=15)
    email = models.EmailField()
    address = models.TextField(blank=True)
    photo = models.ImageField(upload_to='faculty/photos/', blank=True, null=True)
    date_of_joining = models.DateField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.employee_id} - {self.name}"


class FacultyAttendance(models.Model):
    STATUS_CHOICES = [('P', 'Present'), ('A', 'Absent'), ('L', 'Leave'), ('H', 'Holiday')]

    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='attendance')
    date = models.DateField()
    status = models.CharField(max_length=1, choices=STATUS_CHOICES)
    remarks = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ['faculty', 'date']

    def __str__(self):
        return f"{self.faculty.name} - {self.date} - {self.status}"
