from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.utils import timezone
from django.conf import settings


# ---------------------------------------------------------------------------
# Fixed-Duration Session Expiry Middleware
# ---------------------------------------------------------------------------
# Must run AFTER AuthenticationMiddleware, BEFORE FacultyAccessMiddleware.
# Faculty: 120 min from login. All others: 120 min from login.

# Not idle-based — expires regardless of activity.

_EXPIRY_SKIP_PREFIXES = ('/static/', '/media/', '/login/', '/logout/', '/admin/')


class SessionExpiryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            not hasattr(request, 'user')
            or not request.user.is_authenticated
        ):
            return self.get_response(request)

        # Don't check on paths that would cause redirect loops
        if any(request.path.startswith(p) for p in _EXPIRY_SKIP_PREFIXES):
            return self.get_response(request)

        session_id = request.session.get('login_session_id')
        if not session_id:
            return self.get_response(request)

        from .models import LoginSession
        try:
            login_session = LoginSession.objects.get(pk=session_id)
        except LoginSession.DoesNotExist:
            return self.get_response(request)

        # Already closed — force logout
        if not login_session.is_active:
            auth_logout(request)
            messages.error(request, 'Session expired. Please log in again.')
            return redirect('login')

        # Determine limit from role at login time
        role_at_login = login_session.login_role or getattr(request.user, 'role', '')
        faculty_limit = getattr(settings, 'SESSION_EXPIRY_FACULTY_MINUTES', 120)
        other_limit = getattr(settings, 'SESSION_EXPIRY_OTHER_MINUTES', 120)
        limit_minutes = faculty_limit if role_at_login == 'faculty' else other_limit

        elapsed = timezone.now() - login_session.login_time
        if elapsed.total_seconds() > limit_minutes * 60:
            # Close the LoginSession
            login_session.close()
            # Flush the Django session and force logout
            auth_logout(request)
            messages.error(request, 'Session expired. Please log in again.')
            return redirect('login')

        return self.get_response(request)

FACULTY_ALLOWED_PATHS = [
    '/attendance/',
    '/marks/',
    '/lab/',
    '/fees/',
    '/students/',
    '/logout/',
    '/static/',
]


class FacultyAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and hasattr(request.user, 'role')
            and request.user.role == 'faculty'
        ):
            path = request.path
            allowed = any(path.startswith(p) for p in FACULTY_ALLOWED_PATHS)
            if not allowed:
                messages.error(request, "You do not have access to this page.")
                return redirect('/attendance/')
        return self.get_response(request)


# ---------------------------------------------------------------------------
# Activity Log Middleware — logs POST actions per login session
# ---------------------------------------------------------------------------

# Human-readable labels for common URL names
_ACTION_LABELS = {
    'attendance_mark': 'Marked attendance',
    'attendance_save_reasons': 'Saved absence reasons',
    'attendance_send_whatsapp': 'Sent WhatsApp notifications',
    'faculty_add': 'Added a faculty member',
    'faculty_edit': 'Edited a faculty member',
    'faculty_delete': 'Removed a faculty member',
    'faculty_attendance': 'Marked faculty attendance',
    'student_add': 'Added a student',
    'student_edit': 'Edited a student',
    'student_delete': 'Deleted a student',
    'fee_collect': 'Collected a fee payment',
    'group_add': 'Added a group',
    'group_edit': 'Edited a group',
    'group_delete': 'Deleted a group',
    'section_add': 'Added a section',
    'section_edit': 'Edited a section',
    'section_delete': 'Deleted a section',
    'user_add': 'Created a user',
    'user_edit': 'Edited a user',
    'user_toggle': 'Toggled user active status',
    'user_reset_password': 'Reset a user password',
    'login': 'Logged in',
}

# Paths to skip logging entirely
_SKIP_PREFIXES = ('/admin/', '/static/', '/media/', '/__debug__/')


class ActivityLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only log POST from authenticated users
        if (
            request.method != 'POST'
            or not hasattr(request, 'user')
            or not request.user.is_authenticated
        ):
            return response

        # Skip admin/static/media paths
        if any(request.path.startswith(p) for p in _SKIP_PREFIXES):
            return response

        # Skip failed requests (4xx/5xx)
        if response.status_code >= 400:
            return response

        # Resolve the URL name for a human-readable action
        from django.urls import resolve
        try:
            match = resolve(request.path)
            url_name = match.url_name or ''
        except Exception:
            url_name = ''

        action = _ACTION_LABELS.get(url_name, url_name.replace('_', ' ').title() or request.path)

        # Get login session from Django session
        session_id = request.session.get('login_session_id')
        login_session = None
        if session_id:
            from .models import LoginSession
            try:
                login_session = LoginSession.objects.get(pk=session_id)
            except LoginSession.DoesNotExist:
                pass

        from .models import ActivityLog
        try:
            ActivityLog.objects.create(
                session=login_session,
                user=request.user,
                action=action,
                path=request.path,
                method=request.method,
            )
        except Exception as e:
            import logging
            logging.getLogger('django').error(f"ActivityLog creation failed for user {request.user} on path {request.path}: {e}", exc_info=True)
            pass  # Never break the request over logging failures

        return response
