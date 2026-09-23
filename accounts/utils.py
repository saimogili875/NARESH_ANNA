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
