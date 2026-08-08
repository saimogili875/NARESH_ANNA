from django.db import models
from students.models import Student


class PendingMessage(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SENT, 'Sent'),
        (STATUS_FAILED, 'Failed'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, null=True, blank=True, related_name='whatsapp_messages')
    faculty = models.ForeignKey('faculty.Faculty', on_delete=models.SET_NULL, null=True, blank=True, related_name='whatsapp_messages')
    phone = models.CharField(max_length=20)
    message = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = "Pending WhatsApp Message"
        verbose_name_plural = "Pending WhatsApp Messages"

    def __str__(self):
        recipient = self.faculty.name if self.faculty else (self.student.name if self.student else "Unknown")
        return f"{recipient} - {self.phone} - {self.status}"



class WhatsAppSession(models.Model):
    session_data = models.TextField(help_text="Exported Playwright storage_state JSON data")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "WhatsApp Session Storage"
        verbose_name_plural = "WhatsApp Session Storage Records"

    def __str__(self):
        return f"WhatsApp Session (Updated: {self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else 'N/A'})"

