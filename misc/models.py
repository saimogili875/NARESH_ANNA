import base64
import hashlib
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models
from students.models import Student


def _get_fernet():
    secret = getattr(settings, 'SECRET_KEY', 'default_fallback_secret_key')
    key_bytes = hashlib.sha256(secret.encode()).digest()
    key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(key)


def encrypt_value(val):
    if not val:
        return ''
    if str(val).startswith('gAAAAA'):
        return val  # Already encrypted
    f = _get_fernet()
    return f.encrypt(val.encode('utf-8')).decode('utf-8')


def decrypt_value(val):
    if not val:
        return ''
    if not str(val).startswith('gAAAAA'):
        return val  # Unencrypted or legacy
    try:
        f = _get_fernet()
        return f.decrypt(val.encode('utf-8')).decode('utf-8')
    except Exception:
        return val


class StudentExamInfo(models.Model):
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name='exam_info')

    # ── IPE ──────────────────────────────────────────────────────────────────
    ipe_hall_ticket = models.CharField(max_length=30, blank=True, verbose_name='IPE Hall Ticket')

    # 1st Year IPE marks — Telugu & English are common; s3-s6 are group-specific
    ipe_1st_telugu  = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ipe_1st_english = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ipe_1st_s3      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ipe_1st_s4      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ipe_1st_s5      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ipe_1st_s6      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ipe_1st_total   = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    # 2nd Year IPE marks
    ipe_2nd_telugu  = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ipe_2nd_english = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ipe_2nd_s3      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ipe_2nd_s4      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ipe_2nd_s5      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ipe_2nd_s6      = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ipe_2nd_total   = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    # ── EAMCET ───────────────────────────────────────────────────────────────
    eamcet_hall_ticket  = models.CharField(max_length=30, blank=True)
    eamcet_password     = models.CharField(max_length=255, blank=True)
    eamcet_date_of_exam = models.DateField(null=True, blank=True)
    eamcet_marks        = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    eamcet_rank         = models.CharField(max_length=20, blank=True)

    # ── JEE Main ─────────────────────────────────────────────────────────────
    jee_hall_ticket  = models.CharField(max_length=30, blank=True)
    jee_password     = models.CharField(max_length=255, blank=True)
    jee_date_of_exam = models.DateField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    @property
    def decrypted_eamcet_password(self):
        return decrypt_value(self.eamcet_password)

    @property
    def decrypted_jee_password(self):
        return decrypt_value(self.jee_password)

    def save(self, *args, **kwargs):
        if self.eamcet_password:
            self.eamcet_password = encrypt_value(self.eamcet_password)
        if self.jee_password:
            self.jee_password = encrypt_value(self.jee_password)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Exam Info — {self.student.name}"

