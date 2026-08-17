from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.decorators import admin_required, all_roles_required, superuser_required
from django.utils import timezone
from django.db.models import Sum, Count, Q
from .models import User, Group, Section, AcademicYear, LoginSession, parse_user_agent, get_client_ip
from .forms import LoginForm, UserForm, GroupForm, SectionForm, AcademicYearForm
from students.models import Student
from fees.models import FeePayment, StudentFee
from attendance.models import Attendance
from datetime import date as Date
import logging

logger = logging.getLogger(__name__)


def get_axes_cooloff_time(request=None, credentials=None):
    """
    Callable for AXES_COOLOFF_TIME.
    Escalating cooloff time based on failure count:
    - 3 failures: 10 minutes
    - 4 failures: 30 minutes
    - 5 failures: 2 hours
    - 6 failures: 6 hours
    - 7+ failures: 24 hours
    """
    from datetime import timedelta
    from axes.models import AccessAttempt

    username = None
    if credentials and 'username' in credentials:
        username = credentials['username']
    elif request and hasattr(request, 'POST'):
        username = request.POST.get('username')

    ip_address = None
    if request and hasattr(request, 'META'):
        try:
            from axes.helpers import get_client_ip_address
            ip_address = get_client_ip_address(request)
        except Exception:
            pass

    failures = 3
    attempt = None
    if username and ip_address:
        attempt = AccessAttempt.objects.filter(username=username, ip_address=ip_address).first()
    elif username:
        attempt = AccessAttempt.objects.filter(username=username).first()
    elif ip_address:
        attempt = AccessAttempt.objects.filter(ip_address=ip_address).first()

    if attempt and attempt.failures_since_start:
        failures = attempt.failures_since_start

    if failures <= 3:
        return timedelta(minutes=10)
    elif failures == 4:
        return timedelta(minutes=30)
    elif failures == 5:
        return timedelta(hours=2)
    elif failures == 6:
        return timedelta(hours=6)
    else:
        return timedelta(hours=24)


def get_cooloff_message(request, username=None):
    """Generate dynamic lockout message based on cooloff duration."""
    from axes.helpers import get_cool_off
    cooloff = get_cool_off(request)
    if not cooloff:
        return "Too many failed attempts. Your access is locked."
    total_seconds = int(cooloff.total_seconds())
    if total_seconds >= 3600:
        hours = total_seconds // 3600
        duration_str = f"{hours} hour" if hours == 1 else f"{hours} hours"
    elif total_seconds >= 60:
        minutes = total_seconds // 60
        duration_str = f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"
    else:
        duration_str = f"{total_seconds} seconds"
    return f"Too many failed attempts. Your access is locked for {duration_str}."


def axes_admin_whitelist(request, credentials=None):
    """
    Callable for AXES_WHITELIST_CALLABLE.
    Returns True if the attempted login is for an admin user,
    exempting them from django-axes lockout rules.
    """
    username = None
    if credentials and 'username' in credentials:
        username = credentials['username']
    elif request and request.method == 'POST':
        username = request.POST.get('username')
    
    if username:
        try:
            user = User.objects.get(username=username)
            return user.role == 'admin'
        except User.DoesNotExist:
            pass
    return False

def landing_view(request):
    """Public Entrance / Landing Page for Sri NRI Junior College."""
    return render(request, 'landing.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = LoginForm(request.POST or None)

    if request.method == 'POST':
        username = request.POST.get('username', '')

        # Reject autofilled submissions (JS sets human_typed=true on real keystrokes)
        if request.POST.get('human_typed') != 'true':
            messages.error(request, 'Please type your credentials manually. Autofill is not allowed.')
            return render(request, 'accounts/login.html', {'form': LoginForm()})

        # --- Admin manual block check (independent of axes) ---
        is_admin_attempt = False
        try:
            target_user = User.objects.get(username=username)
            is_admin_attempt = target_user.role == 'admin'
            if target_user.is_blocked_by_admin:
                msg = 'Your account has been blocked by admin. Contact admin for more details.'
                if target_user.blocked_reason:
                    msg += f' Reason: {target_user.blocked_reason}'
                messages.error(request, msg)
                return render(request, 'accounts/login.html', {'form': LoginForm()})
        except User.DoesNotExist:
            pass  # Let axes/authenticate handle unknown usernames

        # Check if already locked out by axes (exempt admins)
        from axes.helpers import get_client_ip_address
        from axes.handlers.proxy import AxesProxyHandler
        if not is_admin_attempt and AxesProxyHandler.is_locked(request, credentials={'username': username}):
            messages.error(request, get_cooloff_message(request, username))
            return render(request, 'accounts/login.html', {'form': LoginForm()})

        if not form.is_valid():
            if 'captcha' in form.errors:
                logger.error(f"reCAPTCHA validation failed for username '{username}'")
                for error in form.errors.as_data().get('captcha', []):
                    logger.error(f"reCAPTCHA Error - Code: {error.code}, Message: {error.message}, Params: {error.params}")

            # Captcha or field validation failed — count toward lockout (exempt admins)
            from django.contrib.auth.signals import user_login_failed
            if not is_admin_attempt:
                user_login_failed.send(
                    sender=__name__,
                    credentials={'username': username},
                    request=request,
                )
            # Re-check lockout after this failure
            if not is_admin_attempt and AxesProxyHandler.is_locked(request, credentials={'username': username}):
                messages.error(request, get_cooloff_message(request, username))
                return render(request, 'accounts/login.html', {'form': LoginForm()})
        else:
            user = authenticate(request,
                                username=form.cleaned_data['username'],
                                password=form.cleaned_data['password'])
            if user:
                login(request, user)
                # --- Create LoginSession ---
                ua_raw = request.META.get('HTTP_USER_AGENT', '')
                session_obj = LoginSession.objects.create(
                    user=user,
                    ip_address=get_client_ip(request),
                    device_info=parse_user_agent(ua_raw),
                    user_agent_raw=ua_raw,
                    login_role=user.role,
                )
                request.session['login_session_id'] = session_obj.pk
                if user.role == 'faculty':
                    return redirect('/attendance/')
                return redirect('dashboard')
            else:
                # authenticate() failed — axes already recorded the failure via signal
                if not is_admin_attempt and AxesProxyHandler.is_locked(request, credentials={'username': form.cleaned_data['username']}):
                    messages.error(request, get_cooloff_message(request, form.cleaned_data['username']))
                    return render(request, 'accounts/login.html', {'form': LoginForm()})
                messages.error(request, 'Invalid username or password.')
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    # --- Close LoginSession ---
    session_id = request.session.get('login_session_id')
    if session_id:
        try:
            login_session = LoginSession.objects.get(pk=session_id, is_active=True)
            login_session.close()
        except LoginSession.DoesNotExist:
            pass
    logout(request)
    return redirect('login')


@login_required
def dashboard(request):
    today = timezone.localdate()
    active_year = AcademicYear.objects.filter(is_active=True).first()

    # Date filter for transactions
    date_str = request.GET.get('txn_date', str(today))
    try:
        selected_txn_date = Date.fromisoformat(date_str)
    except Exception:
        selected_txn_date = today

    students_qs = Student.objects.filter(is_active=True)
    total_students = students_qs.count()
    year1_students = students_qs.filter(section__year='1').count()
    year2_students = students_qs.filter(section__year='2').count()

    today_att = Attendance.objects.filter(date=today)
    today_present = today_att.filter(status='P').count()
    today_absent = today_att.filter(status='A').count()

    # FIX: payment_date is a DateField — use direct equality, not __date lookup
    today_payments = FeePayment.objects.filter(payment_date=today)
    today_fee_collection = today_payments.aggregate(total=Sum('amount'))['total'] or 0

    # Transactions for selected date — FIX: same here
    selected_day_payments = FeePayment.objects.filter(
        payment_date=selected_txn_date
    ).select_related('student_fee__student').order_by('-created_at')
    selected_day_total = selected_day_payments.aggregate(total=Sum('amount'))['total'] or 0

    total_fees = StudentFee.objects.aggregate(t=Sum('total_fee'))['t'] or 0
    total_paid = FeePayment.objects.aggregate(t=Sum('amount'))['t'] or 0
    pending_fees = total_fees - total_paid

    recent_students = Student.objects.order_by('-date_of_admission')[:10]

    return render(request, 'accounts/dashboard.html', {
        'total_students': total_students,
        'year1_students': year1_students,
        'year2_students': year2_students,
        'today_present': today_present,
        'today_absent': today_absent,
        'today_fee_collection': today_fee_collection,
        'pending_fees': pending_fees,
        'selected_day_payments': selected_day_payments,
        'selected_day_total': selected_day_total,
        'selected_txn_date': selected_txn_date,
        'recent_students': recent_students,
        'active_year': active_year,
        'today': today,
    })


@all_roles_required
def group_list(request):
    from faculty.models import Faculty
    from attendance.models import Attendance

    today = timezone.localdate()
    date_str = request.GET.get('date', '')
    try:
        selected_date = Date.fromisoformat(date_str) if date_str else today
    except ValueError:
        selected_date = today

    groups = Group.objects.prefetch_related('sections').all()
    total_faculty = Faculty.objects.filter(is_active=True).count()
    total_sections = Section.objects.count()
    total_students = Student.objects.filter(is_active=True).count()

    group_data = []
    for group in groups:
        style = {
            'color': group.color,
            'bg': group.bg_color,
            'border': group.border_color,
            'icon': group.icon,
            'subjects': group.subjects_text
        }
        sections = list(group.sections.all())
        section_count = len(sections)
        students_qs = Student.objects.filter(section__in=sections, is_active=True)
        student_count = students_qs.count()

        att = Attendance.objects.filter(student__in=students_qs, date=selected_date)
        total_att = att.count()
        present_att = att.filter(status='P').count()
        absent_att = att.filter(status='A').count()
        att_pct = round(present_att / total_att * 100) if total_att else 0

        sample = list(students_qs.exclude(photo='').exclude(photo=None)[:4])
        extra = max(0, student_count - 4)

        group_data.append({
            'group': group,
            'style': style,
            'sections': sections,
            'section_count': section_count,
            'student_count': student_count,
            'att_pct': att_pct,
            'present_att': present_att,
            'absent_att': absent_att,
            'total_att': total_att,
            'sample_students': sample,
            'extra_students': extra,
        })

    return render(request, 'accounts/groups.html', {
        'group_data': group_data,
        'total_groups': groups.count(),
        'total_sections': total_sections,
        'total_students': total_students,
        'total_faculty': total_faculty,
        'selected_date': selected_date,
        'today': today,
    })

@admin_required
def group_add(request):
    form = GroupForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Group added.')
        return redirect('group_list')
    return render(request, 'accounts/group_form.html', {'form': form, 'title': 'Add Group'})

@admin_required
def group_edit(request, pk):
    obj = get_object_or_404(Group, pk=pk)
    form = GroupForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, 'Group updated.')
        return redirect('group_list')
    return render(request, 'accounts/group_form.html', {'form': form, 'title': 'Edit Group'})

@admin_required
def group_delete(request, pk):
    get_object_or_404(Group, pk=pk).delete()
    messages.success(request, 'Group deleted.')
    return redirect('group_list')

@admin_required
def section_add(request):
    form = SectionForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Section added.')
        return redirect('group_list')
    return render(request, 'accounts/section_form.html', {'form': form, 'title': 'Add Section'})

@admin_required
def section_edit(request, pk):
    obj = get_object_or_404(Section, pk=pk)
    form = SectionForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, 'Section updated.')
        return redirect('group_list')
    return render(request, 'accounts/section_form.html', {'form': form, 'title': 'Edit Section'})

@admin_required
def section_delete(request, pk):
    get_object_or_404(Section, pk=pk).delete()
    messages.success(request, 'Section deleted.')
    return redirect('group_list')

@superuser_required
def user_list(request):
    users = User.objects.exclude(role='admin').order_by('role', 'username')
    return render(request, 'accounts/user_list.html', {'users': users})

@superuser_required
def user_add(request):
    form = UserForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'User created.')
        return redirect('user_list')
    return render(request, 'accounts/user_form.html', {'form': form, 'title': 'Add User'})

@superuser_required
def user_edit(request, pk):
    obj = get_object_or_404(User, pk=pk)
    form = UserForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, 'User updated.')
        return redirect('user_list')
    return render(request, 'accounts/user_form.html', {'form': form, 'title': 'Edit User'})

@superuser_required
def user_toggle(request, pk):
    obj = get_object_or_404(User, pk=pk)
    obj.is_active = not obj.is_active
    obj.save()
    messages.success(request, f"User {'enabled' if obj.is_active else 'disabled'}.")
    return redirect('user_list')

@superuser_required
def user_reset_password(request, pk):
    obj = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        new_pass = request.POST.get('password')
        obj.set_password(new_pass)
        obj.save()
        messages.success(request, 'Password reset successfully.')
        return redirect('user_list')
    return render(request, 'accounts/reset_password.html', {'obj': obj})
