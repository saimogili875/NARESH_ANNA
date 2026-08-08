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


class AttendanceWindow(models.Model):
    start_time = models.TimeField(default="08:00:00", help_text="Start time for attendance window (e.g. 08:00 AM)")
    end_time = models.TimeField(default="09:00:00", help_text="End time for attendance window (e.g. 09:00 AM)")
    is_active = models.BooleanField(default=True, help_text="Enable time window restrictions for faculty")

    class Meta:
        verbose_name = "Attendance Window Configuration"
        verbose_name_plural = "Attendance Window Configurations"

    def __str__(self):
        s_fmt = self.start_time.strftime("%I:%M %p") if self.start_time else "08:00 AM"
        e_fmt = self.end_time.strftime("%I:%M %p") if self.end_time else "09:00 AM"
        return f"Attendance Window ({s_fmt} - {e_fmt})"

    @classmethod
    def is_currently_open(cls, user=None):
        """
        Check if attendance window is currently open.
        - Admin and Accounts roles are NEVER restricted.
        - Faculty role: restricted to start_time <= current_time <= end_time.
        Returns tuple: (is_open: bool, message: str)
        """
        from datetime import time
        from django.utils import timezone

        if user and (getattr(user, 'is_superuser', False) or getattr(user, 'role', '') in ['admin', 'accounts']):
            return True, "Admin/Accounts role: unrestricted access"

        config = cls.objects.filter(is_active=True).first()
        if not config:
            start_t = time(8, 0)
            end_t = time(9, 0)
        else:
            start_t = config.start_time
            end_t = config.end_time

        now_time = timezone.localtime().time()
        if start_t <= now_time <= end_t:
            return True, "Window open"

        start_str = start_t.strftime("%I:%M %p")
        end_str = end_t.strftime("%I:%M %p")
        return False, f"Attendance window is closed for faculty. Today's allowed window: {start_str} to {end_str}."

