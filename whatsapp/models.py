from django.db import models
from students.models import Student


class PendingMessage(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_SENT = 'sent'
    STATUS_DELIVERED = 'delivered'
    STATUS_READ = 'read'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_SENT, 'Sent'),
        (STATUS_DELIVERED, 'Delivered'),
        (STATUS_READ, 'Read'),
        (STATUS_FAILED, 'Failed'),
    ]

    TYPE_TEMPLATE = 'template'
    TYPE_TEXT = 'text'
    TYPE_CHOICES = [
        (TYPE_TEMPLATE, 'Template'),
        (TYPE_TEXT, 'Text'),
    ]

    CATEGORY_MARKS = 'MARKS'
    CATEGORY_ATTENDANCE = 'ATTENDANCE'
    CATEGORY_OTHER = 'OTHER'
    CATEGORY_CHOICES = [
        (CATEGORY_MARKS, 'Marks'),
        (CATEGORY_ATTENDANCE, 'Attendance'),
        (CATEGORY_OTHER, 'Other'),
    ]

    wamid = models.CharField(max_length=100, blank=True, default='', db_index=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, null=True, blank=True, related_name='whatsapp_messages')
    faculty = models.ForeignKey('faculty.Faculty', on_delete=models.SET_NULL, null=True, blank=True, related_name='whatsapp_messages')
    phone = models.CharField(max_length=20)
    message_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=TYPE_TEMPLATE)
    category = models.CharField(max_length=12, choices=CATEGORY_CHOICES, default=CATEGORY_OTHER, db_index=True)
    group = models.ForeignKey('accounts.Group', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    section = models.ForeignKey('accounts.Section', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    template_name = models.CharField(max_length=100, blank=True, default='')
    template_params = models.JSONField(blank=True, null=True, default=list)
    language = models.CharField(max_length=10, default='en')
    message = models.TextField()  # Fallback or display text preview
    attendance_date = models.DateField(null=True, blank=True, help_text="Date of attendance associated with this message")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = "Pending WhatsApp Message"
        verbose_name_plural = "Pending WhatsApp Messages"
        indexes = [
            models.Index(fields=['category', 'created_at']),
        ]

    def __str__(self):
        recipient = self.faculty.name if self.faculty else (self.student.name if self.student else "Unknown")
        return f"{recipient} - {self.phone} - {self.status}"

    def save(self, *args, **kwargs):
        from django.conf import settings
        from django.utils import timezone

        is_new = self._state.adding or not self.pk

        if is_new:
            # Derive category if OTHER and student is set
            if self.category == self.CATEGORY_OTHER and self.student_id:
                t_name = self.template_name or ''
                exam_templates = {
                    getattr(settings, 'META_TEMPLATE_EXAM_MARKS', 'exam_marks'),
                    'marks_template',
                    'exam_marks',
                }
                absence_templates = {
                    getattr(settings, 'META_TEMPLATE_ABSENCE', 'absence_alert'),
                    'absence_alert',
                }
                if t_name in exam_templates:
                    self.category = self.CATEGORY_MARKS
                elif t_name in absence_templates:
                    self.category = self.CATEGORY_ATTENDANCE
                else:
                    self.category = self.CATEGORY_OTHER

            # Snapshot section and group if student is set and section is empty
            if self.student_id and not self.section_id:
                if self.student and self.student.section:
                    self.section = self.student.section
                    self.group = self.student.section.group

        # Stamp sent_at first time status reaches sent/delivered/read
        if self.sent_at is None and self.status in (self.STATUS_SENT, self.STATUS_DELIVERED, self.STATUS_READ):
            self.sent_at = timezone.now()

        # Handle update_fields if passed
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = set(update_fields)
            if self.sent_at:
                update_fields.add('sent_at')
            if is_new:
                update_fields.update({'category', 'section', 'group'})
            kwargs['update_fields'] = update_fields

        super().save(*args, **kwargs)

    def apply_status_update(self, new_status, event_time=None, error_detail=''):
        from django.utils import timezone
        event_time = event_time or timezone.now()

        RANK = {
            self.STATUS_PENDING: 0,
            self.STATUS_PROCESSING: 1,
            self.STATUS_FAILED: 2,
            self.STATUS_SENT: 3,
            self.STATUS_DELIVERED: 4,
            self.STATUS_READ: 5,
        }

        current_rank = RANK.get(self.status, 0)
        target_rank = RANK.get(new_status, 0)

        should_update_status = False

        if new_status == self.STATUS_FAILED:
            # 'failed' must override pending, processing, sent, failed; MUST NOT override delivered or read
            if self.status in (self.STATUS_PENDING, self.STATUS_PROCESSING, self.STATUS_SENT, self.STATUS_FAILED):
                should_update_status = True
        else:
            if target_rank > current_rank or self.status == self.STATUS_FAILED:
                should_update_status = True

        if should_update_status:
            self.status = new_status

        # Update timestamps
        if new_status == self.STATUS_DELIVERED or self.status == self.STATUS_DELIVERED:
            if not self.delivered_at:
                self.delivered_at = event_time
        if new_status == self.STATUS_READ or self.status == self.STATUS_READ:
            if not self.read_at:
                self.read_at = event_time
            if not self.delivered_at:
                self.delivered_at = event_time
        if self.status in (self.STATUS_SENT, self.STATUS_DELIVERED, self.STATUS_READ):
            if not self.sent_at:
                self.sent_at = event_time

        if error_detail:
            self.error_message = error_detail
        elif new_status == self.STATUS_FAILED and not self.error_message:
            self.error_message = error_detail

        self.save()



class WhatsAppSession(models.Model):
    session_data = models.TextField(help_text="Exported Playwright storage_state JSON data")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "WhatsApp Session Storage"
        verbose_name_plural = "WhatsApp Session Storage Records"

    def __str__(self):
        return f"WhatsApp Session (Updated: {self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else 'N/A'})"

