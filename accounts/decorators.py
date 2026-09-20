from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps

def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role in roles or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('dashboard')
        return wrapper
    return decorator

admin_required = role_required('admin', 'accounts')
admin_accounts_required = role_required('admin', 'accounts')
admin_faculty_required = role_required('admin', 'faculty')
all_roles_required = role_required('admin', 'faculty', 'accounts')


def superuser_required(view_func):
    """Only real Django superusers — not just app-level 'admin' role accounts."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('dashboard')
    return wrapper
