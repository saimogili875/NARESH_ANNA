from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from datetime import date as Date
from .models import Faculty, FacultyAttendance
from accounts.models import User, Section
from marks.models import Subject
from accounts.decorators import admin_required, all_roles_required


@all_roles_required
def faculty_list(request):
    faculty = Faculty.objects.select_related('user').prefetch_related('assigned_sections__group', 'assigned_subjects').filter(is_active=True)
    return render(request, 'faculty/list.html', {'faculty': faculty})


@admin_required
def faculty_add(request):
    users = User.objects.filter(role='faculty').exclude(faculty_profile__isnull=False)
    sections = Section.objects.select_related('group').all()
    all_subjects = Subject.objects.all().order_by('name')
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
        subject_ids = request.POST.getlist('assigned_subjects')
        faculty.assigned_subjects.set(subject_ids)
        messages.success(request, 'Faculty added successfully.')
        return redirect('faculty_list')
    return render(request, 'faculty/form.html', {
        'users': users, 'sections': sections, 'all_subjects': all_subjects, 'title': 'Add Faculty',
    })


@admin_required
def faculty_edit(request, pk):
    obj = get_object_or_404(Faculty, pk=pk)
    sections = Section.objects.select_related('group').all()
    all_subjects = Subject.objects.all().order_by('name')
    assigned_ids = set(obj.assigned_sections.values_list('pk', flat=True))
    assigned_subject_ids = set(obj.assigned_subjects.values_list('pk', flat=True))
    if request.method == 'POST':
        obj.name = request.POST.get('name')
        obj.subject = request.POST.get('subject')
        obj.phone = request.POST.get('phone')
        obj.email = request.POST.get('email')
        obj.address = request.POST.get('address', '')
        obj.save()
        section_ids = request.POST.getlist('assigned_sections')
        obj.assigned_sections.set(section_ids)
        subject_ids = request.POST.getlist('assigned_subjects')
        obj.assigned_subjects.set(subject_ids)
        messages.success(request, 'Faculty updated successfully.')
        return redirect('faculty_list')
    return render(request, 'faculty/form.html', {
        'obj': obj, 'sections': sections, 'assigned_ids': assigned_ids,
        'all_subjects': all_subjects, 'assigned_subject_ids': assigned_subject_ids,
        'title': 'Edit Faculty',
    })


@admin_required
def faculty_delete(request, pk):
    obj = get_object_or_404(Faculty, pk=pk)
    obj.is_active = False
    obj.save()
    messages.success(request, 'Faculty removed.')
    return redirect('faculty_list')


from attendance.views import parse_date_input, trigger_whatsapp_sender_in_background
from whatsapp.models import PendingMessage



@all_roles_required
def faculty_attendance(request):
    today = timezone.localdate()
    date_str = request.GET.get('date', '')
    selected_date = parse_date_input(date_str, default=today)

    faculty_qs = Faculty.objects.filter(is_active=True).select_related('user')
    existing = FacultyAttendance.objects.filter(date=selected_date)
    att_map = {a.faculty_id: a.status for a in existing}

    if request.method == 'POST':
        post_date = request.POST.get('date', '')
        selected_date = parse_date_input(post_date, default=today)
        send_type = request.POST.get('send_whatsapp', '')  # 'absent', 'all', or ''

        for f in faculty_qs:
            status = request.POST.get(f'status_{f.pk}', 'P')
            FacultyAttendance.objects.update_or_create(
                faculty=f, date=selected_date,
                defaults={'status': status}
            )

        messages.success(request, f'Faculty attendance saved for {selected_date.strftime("%d-%m-%Y")}.')

        if send_type in ['absent', 'all'] and (getattr(request.user, 'role', '') == 'admin' or request.user.is_superuser):
            from whatsapp.services import send_faculty_absence_alert, send_generic_template
            target_lang = (request.POST.get('language') or 'en').lower().strip()
            sent_count = 0
            failed_count = 0
            for f in faculty_qs:
                status = request.POST.get(f'status_{f.pk}', 'P')
                if send_type == 'absent' and status != 'A':
                    continue

                phone = (f.phone or getattr(f.user, 'phone', '') or '').strip()

                if not phone:
                    continue

                if status == 'A':
                    result = send_faculty_absence_alert(
                        faculty_name=f.name,
                        phone=phone,
                        date_str=selected_date.strftime('%d-%m-%Y'),
                        language=target_lang,
                    )
                else:
                    result = send_generic_template(
                        to_number=phone,
                        message=(
                            f"Dear {f.name}, Your attendance has been marked PRESENT for today, "
                            f"{selected_date.strftime('%d-%m-%Y')}. Have a great day! - Sri NRI Junior College"
                        ),
                        language=target_lang,
                    )

                if result.get('success'):
                    sent_count += 1
                else:
                    failed_count += 1

            messages.success(request, f'WhatsApp alerts sent: {sent_count} delivered, {failed_count} failed for faculty on {selected_date.strftime("%d-%m-%Y")}.')

        return redirect(f'/faculty/attendance/?date={selected_date.isoformat()}')




    # Map recent WhatsApp messages for selected date
    msgs = PendingMessage.objects.filter(
        faculty__in=faculty_qs,
        created_at__date=selected_date
    ).order_by('-created_at')
    whatsapp_map = {}
    for m in msgs:
        if m.faculty_id not in whatsapp_map:
            whatsapp_map[m.faculty_id] = m

    return render(request, 'faculty/attendance.html', {
        'faculty_qs': faculty_qs,
        'att_map': att_map,
        'whatsapp_map': whatsapp_map,
        'selected_date': selected_date,
        'today': today,
    })

