from django.shortcuts import redirect

FACULTY_ALLOWED_PATHS = [
    '/attendance/',
    '/marks/',
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
                return redirect('/attendance/')
        return self.get_response(request)
