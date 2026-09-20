from django.db.models.signals import post_save
from django.dispatch import receiver
from students.models import Student
from .models import StudentFeeCharge


@receiver(post_save, sender=Student)
def auto_assign_section_fees(sender, instance, **kwargs):
    """When a student is created or their section changes, automatically
    give them any fee type that's already assigned to other students in
    that same section (matching the same amount), if they don't already
    have that charge."""
    if not instance.section_id or not instance.is_active:
        return

    existing_section_charges = (
        StudentFeeCharge.objects
        .filter(student__section_id=instance.section_id, student__is_active=True)
        .exclude(student_id=instance.pk)
        .select_related('fee_type')
    )

    seen_fee_types = {}
    for charge in existing_section_charges:
        if charge.fee_type_id not in seen_fee_types:
            seen_fee_types[charge.fee_type_id] = charge.amount_assigned

    for fee_type_id, amount in seen_fee_types.items():
        StudentFeeCharge.objects.get_or_create(
            student=instance,
            fee_type_id=fee_type_id,
            defaults={'amount_assigned': amount},
        )
