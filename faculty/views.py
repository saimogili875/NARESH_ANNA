from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from datetime import date as Date
from .models import Faculty, FacultyAttendance
from accounts.models import User, Section
from accounts.decorators import admin_required, all_roles_required


@all_roles_required
def faculty_list(request):
    faculty = Faculty.objects.select_related('user').prefetch_related('assigned_sections__group').filter(is_active=True)
    return render(request, 'faculty/list.html', {'faculty': faculty})


@admin_required
def faculty_add(request):
    users = User.objects.filter(role='faculty').exclude(faculty_profile__isnull=False)
    sections = Section.objects.select_related('group').all()
    if request.method == 'POST':
        user_id = request.POST.get('user')
        user = get_object_or_404(User, pk=user_id)
        faculty = Faculty.objects.create(
            user=user,
            employee_id=request.POST.get('employee_id'),
            name=request.POST.get('name'),
            subject=request.POST.get('subject'),
            phone=request.POST.get('phone'),
            email=request.POST.get('email'),
            address=request.POST.get('address', ''),
            date_of_joining=request.POST.get('date_of_joining'),
        )
        section_ids = request.POST.getlist('assigned_sections')
        faculty.assigned_sections.set(section_ids)
        messages.success(request, 'Faculty added successfully.')
        return redirect('faculty_list')
    return render(request, 'faculty/form.html', {
        'users': users, 'sections': sections, 'title': 'Add Faculty',
    })


@admin_required
def faculty_edit(request, pk):
    obj = get_object_or_404(Faculty, pk=pk)
    sections = Section.objects.select_related('group').all()
    assigned_ids = set(obj.assigned_sections.values_list('pk', flat=True))
    if request.method == 'POST':
        obj.name = request.POST.get('name')
        obj.subject = request.POST.get('subject')
        obj.phone = request.POST.get('phone')
        obj.email = request.POST.get('email')
        obj.address = request.POST.get('address', '')
        obj.save()
        section_ids = request.POST.getlist('assigned_sections')
        obj.assigned_sections.set(section_ids)
        messages.success(request, 'Faculty updated successfully.')
        return redirect('faculty_list')
    return render(request, 'faculty/form.html', {
        'obj': obj, 'sections': sections, 'assigned_ids': assigned_ids,
        'title': 'Edit Faculty',
    })


@admin_required
def faculty_delete(request, pk):
    obj = get_object_or_404(Faculty, pk=pk)
    obj.is_active = False
    obj.save()
    messages.success(request, 'Faculty removed.')
    return redirect('faculty_list')


@all_roles_required
def faculty_attendance(request):
    today = timezone.localdate()
    date_str = request.GET.get('date', str(today))
    try:
        selected_date = Date.fromisoformat(date_str)
    except Exception:
        selected_date = today

    faculty_qs = Faculty.objects.filter(is_active=True)
    existing = FacultyAttendance.objects.filter(date=selected_date)
    att_map = {a.faculty_id: a.status for a in existing}

    if request.method == 'POST':
        post_date = request.POST.get('date', str(today))
        try:
            selected_date = Date.fromisoformat(post_date)
        except Exception:
            selected_date = today
        for f in faculty_qs:
            status = request.POST.get(f'status_{f.pk}', 'P')
            FacultyAttendance.objects.update_or_create(
                faculty=f, date=selected_date,
                defaults={'status': status}
            )
        messages.success(request, f'Faculty attendance saved for {selected_date}.')
        return redirect(f'/faculty/attendance/?date={selected_date}')

    return render(request, 'faculty/attendance.html', {
        'faculty_qs': faculty_qs,
        'att_map': att_map,
        'selected_date': selected_date,
        'today': today,
    })
