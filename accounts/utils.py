from accounts.models import Section

def _get_faculty_sections(user):
    """Return the queryset of sections this user is allowed to access.

    - Admin / superuser / accounts → all sections (unrestricted).
    - Faculty → only their assigned_sections.
    - Everyone else → empty queryset.
    """
    if not user or not user.is_authenticated:
        return Section.objects.none()
    if user.is_superuser or user.role in ['admin', 'accounts']:
        return Section.objects.select_related('group').all()
    if user.role == 'faculty':
        try:
            return user.faculty_profile.assigned_sections.select_related('group').all()
        except Exception:
            return Section.objects.none()
    return Section.objects.none()


def _section_allowed(user, section_id):
    """Check if a specific section_id is in the user's allowed set."""
    if user.is_superuser or user.role in ['admin', 'accounts']:
        return True
    return _get_faculty_sections(user).filter(pk=section_id).exists()


def get_group_delete_impact(group):
    """Calculate delete impact metrics for a Group.

    Returns:
      - group: Group instance
      - sections: List of Section objects belonging to the group
      - section_count: Number of sections in this group
      - section_names: List of section display names [str(sec)...]
      - active_students: Number of active students assigned (is_active=True)
      - inactive_students: Number of inactive students assigned (is_active=False)
      - total_students: Total students assigned (active + inactive)
      - category_config_count: Number of GroupCategoryConfig rows linked to group
      - exam_count: Number of Exam rows linked to group
      - can_delete: Boolean (True ONLY if total_students == 0)
      - sections_with_students: List of strings detailing sections with assigned students
    """
    from students.models import Student
    from marks.models import GroupCategoryConfig, Exam

    sections = list(group.sections.select_related('group').all())
    section_count = len(sections)
    section_names = [str(sec) for sec in sections]

    student_qs = Student.objects.filter(section__group=group)
    active_students = student_qs.filter(is_active=True).count()
    inactive_students = student_qs.filter(is_active=False).count()
    total_students = active_students + inactive_students

    category_config_count = GroupCategoryConfig.objects.filter(group=group).count()
    exam_count = Exam.objects.filter(group=group).count()

    can_delete = (total_students == 0)

    sections_with_students = []
    if total_students > 0:
        for sec in sections:
            sec_students = Student.objects.filter(section=sec)
            cnt = sec_students.count()
            if cnt > 0:
                act = sec_students.filter(is_active=True).count()
                inact = sec_students.filter(is_active=False).count()
                details = []
                if act > 0:
                    details.append(f"{act} active")
                if inact > 0:
                    details.append(f"{inact} inactive")
                details_str = ", ".join(details)
                sections_with_students.append(f"{sec} ({cnt} student{'s' if cnt != 1 else ''}: {details_str})")

    return {
        'group': group,
        'sections': sections,
        'section_count': section_count,
        'section_names': section_names,
        'active_students': active_students,
        'inactive_students': inactive_students,
        'total_students': total_students,
        'category_config_count': category_config_count,
        'exam_count': exam_count,
        'can_delete': can_delete,
        'sections_with_students': sections_with_students,
    }

