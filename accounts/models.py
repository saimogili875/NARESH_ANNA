import re

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

class User(AbstractUser):
    ROLE_ADMIN = 'admin'
    ROLE_FACULTY = 'faculty'
    ROLE_ACCOUNTS = 'accounts'

    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Admin'),
        (ROLE_FACULTY, 'Faculty'),
        (ROLE_ACCOUNTS, 'Accounts'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_ADMIN)
    phone = models.CharField(max_length=15, blank=True)
    is_active = models.BooleanField(default=True)

    # Manual admin block (independent of axes auto-lockout)
    is_blocked_by_admin = models.BooleanField(default=False, help_text='Manually blocked by admin')
    blocked_reason = models.TextField(blank=True, help_text='Reason for blocking (shown to user on login)')
    blocked_at = models.DateTimeField(null=True, blank=True)

    def is_admin(self):
        return self.role == self.ROLE_ADMIN

    def is_faculty(self):
        return self.role == self.ROLE_FACULTY

    def is_accounts(self):
        return self.role == self.ROLE_ACCOUNTS

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class AcademicYear(models.Model):
    name = models.CharField(max_length=20)  # e.g. 2024-2025
    is_active = models.BooleanField(default=True)
    start_date = models.DateField()
    end_date = models.DateField()

    def __str__(self):
        return self.name


class Group(models.Model):
    name = models.CharField(max_length=20)  # MPC, BiPC, etc.
    code = models.CharField(max_length=10, unique=True)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, null=True)
    
    # UI Styling fields
    color = models.CharField(max_length=20, default='#374151')
    bg_color = models.CharField(max_length=20, default='#f3f4f6')
    border_color = models.CharField(max_length=20, default='#9ca3af')
    icon = models.CharField(max_length=50, default='bi-grid-fill')
    subjects_text = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.name


class Section(models.Model):
    YEAR_1 = '1'
    YEAR_2 = '2'
    YEAR_CHOICES = [(YEAR_1, '1st Year'), (YEAR_2, '2nd Year')]

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='sections')
    year = models.CharField(max_length=1, choices=YEAR_CHOICES)
    name = models.CharField(max_length=5)  # A, B, C
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, null=True)

    class Meta:
        unique_together = ['group', 'year', 'name', 'academic_year']

    def __str__(self):
        return f"{self.group.code}-{self.year}Y-{self.name}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_user_agent(ua_string):
    """Extract a human-readable 'Browser on OS' string from a User-Agent header.

    Uses regex only — no external dependency required.
    """
    if not ua_string:
        return 'Unknown device'

    # --- OS detection ---
    os_name = 'Unknown OS'
    os_patterns = [
        (r'iPhone.*OS\s([\d_]+)', lambda m: f'iOS {m.group(1).replace("_", ".")}'),
        (r'iPad.*OS\s([\d_]+)', lambda m: f'iPadOS {m.group(1).replace("_", ".")}'),
        (r'Android\s([\d.]+)', lambda m: f'Android {m.group(1)}'),
        (r'Windows NT 10\.0', lambda m: 'Windows 10/11'),
        (r'Windows NT 6\.3', lambda m: 'Windows 8.1'),
        (r'Windows NT 6\.1', lambda m: 'Windows 7'),
        (r'Mac OS X\s([\d_]+)', lambda m: f'macOS {m.group(1).replace("_", ".")}'),
        (r'CrOS', lambda m: 'Chrome OS'),
        (r'Linux', lambda m: 'Linux'),
    ]
    for pattern, formatter in os_patterns:
        match = re.search(pattern, ua_string)
        if match:
            os_name = formatter(match)
            break

    # --- Browser detection (order matters: Edge before Chrome, etc.) ---
    browser_name = 'Unknown browser'
    browser_patterns = [
        (r'Edg[eA]?/([\d.]+)', 'Edge'),
        (r'OPR/([\d.]+)', 'Opera'),
        (r'Vivaldi/([\d.]+)', 'Vivaldi'),
        (r'Firefox/([\d.]+)', 'Firefox'),
        (r'Chrome/([\d.]+)', 'Chrome'),
        (r'Version/([\d.]+).*Safari', 'Safari'),
        (r'Safari/([\d.]+)', 'Safari'),
    ]
    for pattern, name in browser_patterns:
        match = re.search(pattern, ua_string)
        if match:
            version = match.group(1).split('.')[0]  # major version only
            browser_name = f'{name} {version}'
            break

    return f'{browser_name} on {os_name}'


def get_client_ip(request):
    """Extract client IP, respecting X-Forwarded-For from reverse proxies (Render, etc.)."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


# ---------------------------------------------------------------------------
# Login Session
# ---------------------------------------------------------------------------

class LoginSession(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='login_sessions',
    )
    ip_address = models.GenericIPAddressField()
    device_info = models.CharField(max_length=255, help_text='Parsed browser + OS from User-Agent')
    user_agent_raw = models.TextField(blank=True, help_text='Full raw User-Agent string')
    login_time = models.DateTimeField(auto_now_add=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    login_role = models.CharField(
        max_length=20, blank=True, default='',
        help_text='User role at login time — used for session expiry limits',
    )

    class Meta:
        ordering = ['-login_time']

    def __str__(self):
        status = 'active' if self.is_active else 'ended'
        return f"{self.user.username} — {self.login_time:%d %b %Y %H:%M} ({status})"

    @property
    def duration(self):
        """Return session duration as a timedelta.

        If session is still active, returns time elapsed since login.
        """
        end = self.logout_time or timezone.now()
        return end - self.login_time

    @property
    def duration_display(self):
        """Human-readable duration string, e.g. '2h 15m' or '45m'."""
        total_seconds = int(self.duration.total_seconds())
        if total_seconds < 0:
            return '—'
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        if hours > 0:
            return f'{hours}h {minutes}m'
        return f'{minutes}m'

    def close(self):
        """Close the session — called on logout or expiry."""
        self.logout_time = timezone.now()
        self.is_active = False
        self.save(update_fields=['logout_time', 'is_active'])


# ---------------------------------------------------------------------------
# Activity Log
# ---------------------------------------------------------------------------

class ActivityLog(models.Model):
    session = models.ForeignKey(
        LoginSession, on_delete=models.CASCADE,
        related_name='activities', null=True, blank=True,
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='activity_logs',
    )
    action = models.CharField(max_length=255)
    path = models.CharField(max_length=500)
    method = models.CharField(max_length=10)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.username}: {self.action} ({self.timestamp:%H:%M:%S})"
