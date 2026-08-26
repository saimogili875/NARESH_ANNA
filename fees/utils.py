from fees.models import StudentFeeCharge
from accounts.models import AcademicYear

def sync_student_section_fees(student):
    """
    Auto-assign active section-level fee types (e.g. Material Fee, Exam Fee) to a student.
    Finds all FeeTypes assigned to other students in student.section for the active/student academic year.
    For any FeeType where the student does NOT yet have a charge, creates a StudentFeeCharge using 
    the standard amount_assigned assigned to other students in that section.
    """
    if not student or not student.section:
        return 0

    active_year = student.academic_year or AcademicYear.objects.filter(is_active=True).first()
    if not active_year:
        return 0

    other_charges = StudentFeeCharge.objects.filter(
        student__section=student.section,
        fee_type__academic_year=active_year
    ).exclude(student=student)

    fee_type_amounts = {}
    for c in other_charges:
        if c.fee_type_id not in fee_type_amounts:
            fee_type_amounts[c.fee_type_id] = (c.fee_type, c.amount_assigned)

    created_count = 0
    for fee_type_id, (fee_type, amount) in fee_type_amounts.items():
        charge, created = StudentFeeCharge.objects.get_or_create(
            student=student,
            fee_type=fee_type,
            defaults={'amount_assigned': amount}
        )
        if created:
            created_count += 1

    return created_count
