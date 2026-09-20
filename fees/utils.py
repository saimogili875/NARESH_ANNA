from fees.models import StudentFeeCharge
from accounts.models import AcademicYear

def sync_student_section_fees(student):
    """
    Auto-assign active section-level fee types (e.g. Material Fee, Exam Fee) to a student.
    Finds all FeeTypes assigned to other students in student.section for the active/student academic year.
    For any FeeType where the student does NOT yet have a charge, creates a StudentFeeCharge using 
    the standard amount_assigned assigned to other students in that section.
    """
    section_id = getattr(student, 'section_id', None)
    if not student or not section_id:
        return 0

    active_year = student.academic_year or AcademicYear.objects.filter(is_active=True).first()
    if not active_year:
        return 0

    other_charges = StudentFeeCharge.objects.filter(
        student__section_id=section_id
    ).exclude(student_id=student.pk).select_related('fee_type')

    fee_type_amounts = {}
    for c in other_charges:
        if c.fee_type_id not in fee_type_amounts:
            fee_type_amounts[c.fee_type_id] = (c.fee_type, c.amount_assigned)

    if not fee_type_amounts:
        return 0

    existing_fee_type_ids = set(
        StudentFeeCharge.objects.filter(student_id=student.pk).values_list('fee_type_id', flat=True)
    )

    new_charges = []
    for fee_type_id, (fee_type, amount) in fee_type_amounts.items():
        if fee_type_id not in existing_fee_type_ids:
            new_charges.append(StudentFeeCharge(
                student=student,
                fee_type=fee_type,
                amount_assigned=amount
            ))

    if new_charges:
        StudentFeeCharge.objects.bulk_create(new_charges)
        return len(new_charges)

    return 0
