from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_ADMIN = 'admin'
    ROLE_FACULTY = 'faculty'
    ROLE_ACCOUNTS = 'accounts'

    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Admin'),
        (ROLE_FACULTY, 'Faculty'),
        (ROLE_ACCOUNTS, 'Accounts'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_ADMIN)
    phone = models.CharField(max_length=15, blank=True)
    is_active = models.BooleanField(default=True)

    def is_admin(self):
        return self.role == self.ROLE_ADMIN

    def is_faculty(self):
        return self.role == self.ROLE_FACULTY

    def is_accounts(self):
        return self.role == self.ROLE_ACCOUNTS

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class AcademicYear(models.Model):
    name = models.CharField(max_length=20)  # e.g. 2024-2025
    is_active = models.BooleanField(default=True)
    start_date = models.DateField()
    end_date = models.DateField()

    def __str__(self):
        return self.name


class Group(models.Model):
    name = models.CharField(max_length=20)  # MPC, BiPC, etc.
    code = models.CharField(max_length=10, unique=True)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, null=True)
    
    # UI Styling fields
    color = models.CharField(max_length=20, default='#374151')
    bg_color = models.CharField(max_length=20, default='#f3f4f6')
    border_color = models.CharField(max_length=20, default='#9ca3af')
    icon = models.CharField(max_length=50, default='bi-grid-fill')
    subjects_text = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.name


class Section(models.Model):
    YEAR_1 = '1'
    YEAR_2 = '2'
    YEAR_CHOICES = [(YEAR_1, '1st Year'), (YEAR_2, '2nd Year')]

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='sections')
    year = models.CharField(max_length=1, choices=YEAR_CHOICES)
    name = models.CharField(max_length=5)  # A, B, C
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, null=True)

    class Meta:
        unique_together = ['group', 'year', 'name', 'academic_year']

    def __str__(self):
        return f"{self.group.code}-{self.year}Y-{self.name}"
