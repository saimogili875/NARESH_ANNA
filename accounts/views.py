from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from accounts.decorators import admin_required, all_roles_required, superuser_required
from django.utils import timezone
from django.db.models import Sum, Count, Q
from .models import User, Group, Section, AcademicYear, LoginSession, LoginLog, parse_user_agent, get_client_ip
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
    """Admin accounts follow standard axes lockout rules."""
    return False


def landing_view(request):
    """Public Entrance / Landing Page for Sri NRI Junior College."""
    return render(request, 'landing.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = LoginForm(request.POST or None)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        ip_addr = get_client_ip(request)
        ua_raw = request.META.get('HTTP_USER_AGENT', '')
        device_str = parse_user_agent(ua_raw)

        # Reject autofilled submissions (JS sets human_typed=true on real keystrokes)
        if request.POST.get('human_typed') != 'true':
            messages.warning(request, 'Please type your credentials manually. Autofill is not allowed.')
            return render(request, 'accounts/login.html', {'form': LoginForm()})

        # --- Admin manual block check (independent of axes) ---
        try:
            target_user = User.objects.get(username=username)
            if target_user.is_blocked_by_admin:
                msg = 'Your account has been blocked by admin. Contact admin for more details.'
                if target_user.blocked_reason:
                    msg += f' Reason: {target_user.blocked_reason}'
                LoginLog.objects.create(
                    username=username, user=target_user, status='BLOCKED',
                    failure_reason=f'Account blocked by admin ({target_user.blocked_reason or "No reason specified"})',
                    ip_address=ip_addr, device_info=device_str, user_agent_raw=ua_raw
                )
                messages.error(request, msg)
                return render(request, 'accounts/login.html', {'form': LoginForm()})
        except User.DoesNotExist:
            pass  # Let axes/authenticate handle unknown usernames

        # Check if already locked out by axes
        from axes.helpers import get_client_ip_address
        from axes.handlers.proxy import AxesProxyHandler
        if AxesProxyHandler.is_locked(request, credentials={'username': username}):
            LoginLog.objects.create(
                username=username, status='FAILED', failure_reason='Locked out due to repeated failed attempts',
                ip_address=ip_addr, device_info=device_str, user_agent_raw=ua_raw
            )
            messages.error(request, get_cooloff_message(request, username))
            return render(request, 'accounts/login.html', {'form': LoginForm()})

        if not form.is_valid():
            if 'captcha' in form.errors:
                logger.error(f"reCAPTCHA validation failed for username '{username}'")
                for error in form.errors.as_data().get('captcha', []):
                    logger.error(f"reCAPTCHA Error - Code: {error.code}, Message: {error.message}, Params: {error.params}")

            # Captcha or field validation failed — count toward lockout
            from django.contrib.auth.signals import user_login_failed
            user_login_failed.send(
                sender=__name__,
                credentials={'username': username},
                request=request,
            )
            LoginLog.objects.create(
                username=username, status='FAILED', failure_reason='reCAPTCHA or form validation failed',

                ip_address=ip_addr, device_info=device_str, user_agent_raw=ua_raw
            )
            # Re-check lockout after this failure
            if AxesProxyHandler.is_locked(request, credentials={'username': username}):
                messages.error(request, get_cooloff_message(request, username))
                return render(request, 'accounts/login.html', {'form': LoginForm()})
        else:
            user = authenticate(request,
                                username=form.cleaned_data['username'],
                                password=form.cleaned_data['password'])
            if user:
                login(request, user)
                # --- Create LoginSession & LoginLog ---
                session_obj = LoginSession.objects.create(
                    user=user,
                    ip_address=ip_addr,
                    device_info=device_str,
                    user_agent_raw=ua_raw,
                    login_role=user.role,
                )
                LoginLog.objects.create(
                    username=user.username, user=user, status='SUCCESS', failure_reason='',
                    ip_address=ip_addr, device_info=device_str, user_agent_raw=ua_raw
                )
                request.session['login_session_id'] = session_obj.pk
                if user.role == 'faculty':
                    return redirect('/attendance/')
                return redirect('dashboard')
            else:
                target_user = User.objects.filter(username=form.cleaned_data['username']).first()
                reason = 'Invalid password' if target_user else 'Username does not exist'
                LoginLog.objects.create(
                    username=form.cleaned_data['username'], user=target_user, status='FAILED', failure_reason=reason,
                    ip_address=ip_addr, device_info=device_str, user_agent_raw=ua_raw
                )
                if AxesProxyHandler.is_locked(request, credentials={'username': form.cleaned_data['username']}):
                    messages.error(request, get_cooloff_message(request, form.cleaned_data['username']))
                    return render(request, 'accounts/login.html', {'form': LoginForm()})

                messages.error(request, 'Invalid username or password.')
    return render(request, 'accounts/login.html', {'form': form})


@admin_required
def login_logs_view(request):
    """View to monitor successful and failed login attempts with search and filter."""
    from axes.models import AccessAttempt

    status_filter = request.GET.get('status', '').upper().strip()
    q = request.GET.get('q', '').strip()

    if request.method == 'POST' and 'reset_axes' in request.POST:
        attempt_id = request.POST.get('attempt_id')
        if attempt_id:
            AccessAttempt.objects.filter(pk=attempt_id).delete()
            messages.success(request, 'Lockout attempt cleared successfully.')
            return redirect('login_logs')

    logs = LoginLog.objects.select_related('user').all()
    if status_filter:
        logs = logs.filter(status=status_filter)
    if q:
        logs = logs.filter(
            Q(username__icontains=q) | Q(ip_address__icontains=q) | Q(device_info__icontains=q)
        )

    locked_attempts = AccessAttempt.objects.all().order_by('-attempt_time')

    return render(request, 'accounts/login_logs.html', {
        'logs': logs[:200],
        'status_filter': status_filter,
        'q': q,
        'locked_attempts': locked_attempts,
    })


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
        'total_paid': total_paid,
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
    q = request.GET.get('q', '').strip()
    date_str = request.GET.get('date', '')
    try:
        selected_date = Date.fromisoformat(date_str) if date_str else today
    except ValueError:
        selected_date = today

    active_year = AcademicYear.objects.filter(is_active=True).first()

    # Ensure all 4 core academic streams exist in the database
    DEFAULT_GROUPS = [
        {'name': 'MPC', 'code': 'MPC', 'subjects_text': 'Maths, Physics, Chemistry'},
        {'name': 'BiPC', 'code': 'BIPC', 'subjects_text': 'Biology, Physics, Chemistry'},
        {'name': 'CEC', 'code': 'CEC', 'subjects_text': 'Civics, Economics, Commerce'},
        {'name': 'MEC', 'code': 'MEC', 'subjects_text': 'Maths, Economics, Commerce'},
    ]

    for dg in DEFAULT_GROUPS:
        grp, grp_created = Group.objects.get_or_create(
            code=dg['code'],
            defaults={
                'name': dg['name'],
                'subjects_text': dg['subjects_text'],
                'academic_year': active_year
            }
        )
        if grp_created:
            Section.objects.get_or_create(group=grp, year='1', name='A', defaults={'academic_year': active_year})
            Section.objects.get_or_create(group=grp, year='2', name='A', defaults={'academic_year': active_year})

    groups_qs = Group.objects.prefetch_related('sections').all()
    if q:
        groups_qs = groups_qs.filter(
            Q(name__icontains=q) |
            Q(code__icontains=q) |
            Q(sections__name__icontains=q) |
            Q(sections__year__icontains=q)
        ).distinct()
    groups = groups_qs.order_by('id')
    total_faculty = Faculty.objects.filter(is_active=True).count()
    total_sections = Section.objects.count()
    total_students = Student.objects.filter(is_active=True).count()

    STREAM_THEMES = {
        'MPC': {
            'color': '#1d4ed8', 'bg': '#eff6ff', 'border': '#3b82f6',
            'gradient': 'linear-gradient(135deg, #1e40af, #3b82f6)',
            'image': 'images/stream_mpc.jpg', 'icon': 'bi-calculator-fill'
        },
        'BIPC': {
            'color': '#047857', 'bg': '#ecfdf5', 'border': '#10b981',
            'gradient': 'linear-gradient(135deg, #065f46, #10b981)',
            'image': 'images/stream_bipc.jpg', 'icon': 'bi-heart-pulse-fill'
        },
        'CEC': {
            'color': '#7e22ce', 'bg': '#faf5ff', 'border': '#a855f7',
            'gradient': 'linear-gradient(135deg, #6b21a8, #a855f7)',
            'image': 'images/stream_cec.jpg', 'icon': 'bi-briefcase-fill'
        },
        'MEC': {
            'color': '#c2410c', 'bg': '#fff7ed', 'border': '#f97316',
            'gradient': 'linear-gradient(135deg, #9a3412, #f97316)',
            'image': 'images/stream_mec.jpg', 'icon': 'bi-graph-up-arrow'
        },
    }

    # --- High-Performance Aggregation Algorithm (0 N+1 Queries) ---
    student_counts_by_section = {
        r['section_id']: r['cnt']
        for r in Student.objects.filter(is_active=True).values('section_id').annotate(cnt=Count('id'))
    }

    att_counts_by_section = {}
    for r in Attendance.objects.filter(date=selected_date).values('section_id', 'status').annotate(cnt=Count('id')):
        att_counts_by_section.setdefault(r['section_id'], {})[r['status']] = r['cnt']

    sample_photos_by_section = {}
    sample_qs = (
        Student.objects.filter(is_active=True)
        .exclude(photo='')
        .exclude(photo=None)
        .only('id', 'name', 'photo', 'section_id')
    )
    for st in sample_qs:
        sec_id = st.section_id
        if sec_id and len(sample_photos_by_section.setdefault(sec_id, [])) < 4:
            sample_photos_by_section[sec_id].append(st)

    group_data = []
    for group in groups:
        code_upper = (group.code or '').upper().strip()
        theme = STREAM_THEMES.get(code_upper, {
            'color': group.color if group.color and group.color != '#374151' else '#1d4ed8',
            'bg': group.bg_color if group.bg_color and group.bg_color != '#f3f4f6' else '#eff6ff',
            'border': group.border_color if group.border_color and group.border_color != '#9ca3af' else '#3b82f6',
            'gradient': 'linear-gradient(135deg, #1d4ed8, #3b82f6)',
            'image': 'images/stream_mpc.jpg',
            'icon': group.icon or 'bi-grid-fill'
        })
        style = {
            'color': theme['color'],
            'bg': theme['bg'],
            'border': theme['border'],
            'gradient': theme['gradient'],
            'image': theme['image'],
            'icon': theme['icon'],
            'subjects': group.subjects_text or 'Maths, Physics, Chemistry'
        }
        sections = list(group.sections.all())
        section_count = len(sections)

        # In-memory aggregation per group
        student_count = sum(student_counts_by_section.get(sec.pk, 0) for sec in sections)
        present_att = sum(att_counts_by_section.get(sec.pk, {}).get('P', 0) for sec in sections)
        absent_att = sum(att_counts_by_section.get(sec.pk, {}).get('A', 0) for sec in sections)
        total_att = present_att + absent_att
        att_pct = round(present_att / total_att * 100) if total_att else 0

        # Sample student photos across sections
        sample = []
        for sec in sections:
            sample.extend(sample_photos_by_section.get(sec.pk, []))
            if len(sample) >= 4:
                break
        sample = sample[:4]
        extra = max(0, student_count - len(sample))

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
        'q': q,
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
@require_POST
def group_delete(request, pk):
    group = get_object_or_404(Group, pk=pk)
    sections = group.sections.all()
    section_count = sections.count()
    student_count = Student.objects.filter(section__group=group).count()

    if student_count > 0:
        messages.error(
            request,
            f'Cannot delete group "{group.name}": {student_count} student(s) across {section_count} section(s) '
            f'are assigned to this group. Please reassign or remove the students first.'
        )
        return redirect('group_list')

    group_name = group.name
    try:
        group.delete()
        messages.success(request, f'Group "{group_name}" deleted successfully.')
    except Exception as e:
        messages.error(request, f'Could not delete group "{group_name}": {e}')
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
@require_POST
def section_delete(request, pk):
    sec = get_object_or_404(Section, pk=pk)
    sec_name = str(sec)
    student_count = Student.objects.filter(section=sec).count()

    if student_count > 0:
        messages.error(
            request,
            f'Cannot delete section "{sec_name}": {student_count} student(s) '
            f'are assigned to this section. Please reassign or remove the students first.'
        )
        return redirect('group_list')

    try:
        sec.delete()
        messages.success(request, f'Section "{sec_name}" deleted successfully.')
    except Exception as e:
        messages.error(request, f'Could not delete section "{sec_name}": {e}')
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
@require_POST
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
        new_pass = request.POST.get('password', '').strip()
        if not new_pass:
            messages.error(request, 'Password cannot be blank.')
            return render(request, 'accounts/reset_password.html', {'obj': obj})
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        try:
            validate_password(new_pass, user=obj)
        except ValidationError as e:
            for err in e.messages:
                messages.error(request, err)
            return render(request, 'accounts/reset_password.html', {'obj': obj})

        obj.set_password(new_pass)
        obj.save()
        messages.success(request, 'Password reset successfully.')
        return redirect('user_list')
    return render(request, 'accounts/reset_password.html', {'obj': obj})
