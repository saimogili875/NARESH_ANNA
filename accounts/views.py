from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.decorators import admin_required, all_roles_required
from django.utils import timezone
from django.db.models import Sum, Count, Q
from .models import User, Group, Section, AcademicYear
from .forms import LoginForm, UserForm, GroupForm, SectionForm, AcademicYearForm
from students.models import Student
from fees.models import FeePayment, StudentFee
from attendance.models import Attendance
from datetime import date as Date


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = authenticate(request,
                            username=form.cleaned_data['username'],
                            password=form.cleaned_data['password'])
        selected_role = form.cleaned_data['role']
        if user and user.role == selected_role:
            login(request, user)
            if user.role == 'faculty':
                return redirect('/attendance/')
            return redirect('dashboard')
        elif user and user.role != selected_role:
            messages.error(request, 'Selected role does not match your account.')
        else:
            messages.error(request, 'Invalid username or password.')
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
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

@admin_required
def user_list(request):
    users = User.objects.exclude(role='admin').order_by('role', 'username')
    return render(request, 'accounts/user_list.html', {'users': users})

@admin_required
def user_add(request):
    form = UserForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'User created.')
        return redirect('user_list')
    return render(request, 'accounts/user_form.html', {'form': form, 'title': 'Add User'})

@admin_required
def user_edit(request, pk):
    obj = get_object_or_404(User, pk=pk)
    form = UserForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, 'User updated.')
        return redirect('user_list')
    return render(request, 'accounts/user_form.html', {'form': form, 'title': 'Edit User'})

@admin_required
def user_toggle(request, pk):
    obj = get_object_or_404(User, pk=pk)
    obj.is_active = not obj.is_active
    obj.save()
    messages.success(request, f"User {'enabled' if obj.is_active else 'disabled'}.")
    return redirect('user_list')

@admin_required
def user_reset_password(request, pk):
    obj = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        new_pass = request.POST.get('password')
        obj.set_password(new_pass)
        obj.save()
        messages.success(request, 'Password reset successfully.')
        return redirect('user_list')
    return render(request, 'accounts/reset_password.html', {'obj': obj})
