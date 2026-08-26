from django.db.models.signals import post_save
from django.dispatch import receiver
from students.models import Student
from fees.utils import sync_student_section_fees

@receiver(post_save, sender=Student)
def auto_sync_student_section_fees(sender, instance, created, **kwargs):
    """
    Whenever a Student is saved (created, updated, transferred, imported, or promoted),
    automatically sync all active section-level fee heads to the student.
    """
    if instance.section_id:
        try:
            sync_student_section_fees(instance)
        except Exception:
            pass
