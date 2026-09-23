from django.http import HttpResponse


def privacy_policy(request):
    html = """<!DOCTYPE html>
<html><head><title>Privacy Policy - Sri NRI Junior College</title>
<style>body{font-family:Arial,sans-serif;max-width:800px;margin:40px auto;padding:0 20px;line-height:1.6;color:#333}h1{color:#1a237e}</style>
</head><body>
<h1>Privacy Policy</h1>
<p><strong>Sri NRI Junior College</strong> (operated by Sri Vigneswara Educational Society) uses the WhatsApp Business API to communicate with parents and guardians of enrolled students.</p>
<h2>Information We Collect</h2>
<p>We collect parent/guardian phone numbers provided during student admission for the sole purpose of sending attendance notifications and exam reminders.</p>
<h2>How We Use Your Information</h2>
<ul>
<li>Sending absence alerts when a student is marked absent</li>
<li>Sending weekly exam schedule reminders</li>
<li>Sending fee receipts</li>
</ul>
<h2>Data Sharing</h2>
<p>We do not sell or share your personal data with third parties. Messages are sent via the official Meta WhatsApp Business API.</p>
<h2>Data Retention</h2>
<p>Phone numbers are retained only while the student is enrolled at the college.</p>
<h2>Contact</h2>
<p>For questions about this policy, contact us at: Sri NRI Junior College, Guntur, Andhra Pradesh.</p>
<p><em>Last updated: August 2026</em></p>
</body></html>"""
    return HttpResponse(html)


import os
import mimetypes
from django.conf import settings
from django.http import HttpResponse, FileResponse, Http404
from accounts.utils import _get_faculty_sections

def protected_media(request, path):
    """
    Authorized file server for MEDIA_ROOT files.
    Enforces role and section-level access control on student/faculty photos and private media.
    """
    if not request.user.is_authenticated:
        return HttpResponse("Unauthorized", status=401)

    safe_path = os.path.normpath(path).lstrip('/')
    if safe_path.startswith('..'):
        return HttpResponse("Forbidden", status=403)

    full_path = os.path.join(settings.MEDIA_ROOT, safe_path)
    if not os.path.exists(full_path) or os.path.isdir(full_path):
        raise Http404("Media file not found")

    # Access control checks
    role = getattr(request.user, 'role', '')
    is_admin_or_accounts = getattr(request.user, 'is_superuser', False) or role in ['admin', 'accounts']

    if safe_path.startswith('students/photos/'):
        if not is_admin_or_accounts:
            filename = os.path.basename(safe_path)
            from students.models import Student
            student = Student.objects.filter(photo__icontains=filename).first()
            if student:
                allowed_sections = _get_faculty_sections(request.user)
                if student.section not in allowed_sections:
                    return HttpResponse("Access Denied", status=403)
            else:
                return HttpResponse("Access Denied", status=403)

    elif safe_path.startswith('faculty/photos/'):
        if not is_admin_or_accounts and role != 'faculty':
            return HttpResponse("Access Denied", status=403)

    content_type, _ = mimetypes.guess_type(full_path)
    content_type = content_type or 'application/octet-stream'
    return FileResponse(open(full_path, 'rb'), content_type=content_type)
