from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from datetime import date, datetime
from django.db import transaction
from django.db.models import Count, Q
from django.urls import reverse
from django.contrib.auth import authenticate, login
from urllib.parse import urlencode
import json
from .models import Attendance, AttendanceWindow
from students.models import Student
from accounts.models import Section
from accounts.decorators import all_roles_required, admin_faculty_required, admin_required
from whatsapp.models import PendingMessage



def parse_date_input(date_str, default=None):
    if not date_str:
        return default
    if isinstance(date_str, date):
        return date_str
    date_str = str(date_str).strip()
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        pass

    # NOTE: All templates emit ISO format (Y-m-d) via |date:'Y-m-d' filter.
    # Only non-ISO formats kept here are ones Django can produce on localized
    # rendering (abbreviated/full month strings). %m/%d/%Y removed — it is
    # ambiguous with %d/%m/%Y and no template produces it.
    formats = [
        "%B %d, %Y",   # August 4, 2026 — Django full-month locale format
        "%b. %d, %Y",  # Aug. 4, 2026   — Django abbreviated with dot
        "%b %d, %Y",   # Aug 4, 2026    — Django abbreviated without dot
        "%d/%m/%Y",    # 04/08/2026     — day-first slash (kept for safety)
        "%d-%m-%Y",    # 04-08-2026     — day-first dash
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except (ValueError, TypeError):
            pass
    return default


def _get_faculty_sections(user):
    """Return the queryset of sections this user is allowed to access.

    - Admin / superuser / accounts → all sections (unrestricted).
    - Faculty → only their assigned_sections.
    - Everyone else → empty queryset.
    """
    if user.is_superuser or user.role in ['admin', 'accounts']:
        return Section.objects.select_related('group').all()
    if user.role == 'faculty':
        try:
            return user.faculty_profile.assigned_sections.select_related('group').all()
        except Exception:
            return Section.objects.none()
    return Section.objects.none()


def _section_allowed(user, section_id):
    """Check if a specific section_id is in the user's allowed set."""
    if user.is_superuser or user.role in ['admin', 'accounts']:
        return True
    return _get_faculty_sections(user).filter(pk=section_id).exists()



@all_roles_required
def attendance_list(request):
    today = timezone.localdate()
    date_str = request.GET.get('date', '')
    section_id = request.GET.get('section', '')

    selected_date = parse_date_input(date_str, default=today)

    sections = _get_faculty_sections(request.user)
    students = []
    attendance_map = {}
    remarks_map = {}
    selected_section = None
    is_locked = False
    absent_students = []
    stats = {'present': 0, 'absent': 0, 'not_marked': 0}

    absent_reason_map = {}
    _label_to_key = {'Health Issue': 'health', 'Went Out': 'went_out'}

    if section_id and str(section_id).isdigit():
        if not _section_allowed(request.user, section_id):
            messages.error(request, 'You do not have access to that section.')
            return redirect('attendance_list')
        selected_section = get_object_or_404(Section, pk=section_id)
        students = list(Student.objects.filter(section=selected_section, is_active=True))
        existing = Attendance.objects.filter(student__in=students, date=selected_date)
        attendance_map = {a.student_id: a.status for a in existing}
        remarks_map = {a.student_id: a.remarks for a in existing}
        is_locked = existing.exists()
        stats['present'] = sum(1 for s in students if attendance_map.get(s.pk) == 'P')
        stats['absent'] = sum(1 for s in students if attendance_map.get(s.pk) == 'A')
        stats['not_marked'] = sum(1 for s in students if s.pk not in attendance_map)
        if is_locked:
            absent_students = [s for s in students if attendance_map.get(s.pk) == 'A']
            for s in absent_students:
                remark = remarks_map.get(s.pk) or ''
                if remark in _label_to_key:
                    absent_reason_map[s.pk] = _label_to_key[remark]
                elif remark == '':
                    absent_reason_map[s.pk] = 'no_reason'
                else:
                    absent_reason_map[s.pk] = 'other'

    return render(request, 'attendance/list.html', {
        'sections': sections, 'students': students,
        'attendance_map': attendance_map, 'remarks_map': remarks_map,
        'selected_date': selected_date,
        'selected_section': selected_section, 'section_id': str(section_id),
        'stats': stats, 'today': today,
        'is_locked': is_locked, 'absent_students': absent_students,
        'absent_reason_map': absent_reason_map,
    })


@all_roles_required
def attendance_mark(request):
    if request.method == 'POST':
        # Time lock: faculty can't mark attendance after cutoff
        if request.user.role == 'faculty':
            from django.conf import settings as conf
            now = timezone.localtime()
            cutoff_h = getattr(conf, 'ATTENDANCE_CUTOFF_HOUR', 11)
            cutoff_m = getattr(conf, 'ATTENDANCE_CUTOFF_MINUTE', 0)
            cutoff = now.replace(hour=cutoff_h, minute=cutoff_m, second=0, microsecond=0)
            if now > cutoff:
                time_str = cutoff.strftime('%I:%M %p').lstrip('0')
                messages.error(
                    request,
                    f'Attendance marking is locked after {time_str}. Please contact admin.'
                )
                return redirect('attendance_list')

        section_id = request.POST.get('section_id')
        date_str = request.POST.get('date')

        if not section_id or not str(section_id).isdigit():
            messages.error(request, "Invalid section.")
            return redirect('attendance_list')

        # --- Section restriction ---
        if not _section_allowed(request.user, section_id):
            messages.error(request, 'You do not have access to that section.')
            return redirect('attendance_list')

        section = get_object_or_404(Section, pk=section_id)

        selected_date = parse_date_input(date_str)
        if not selected_date:
            messages.error(request, "Invalid date format.")
            return redirect('attendance_list')

        students = Student.objects.filter(section=section, is_active=True)

        _reason_labels = {
            'health': 'Health Issue',
            'went_out': 'Went Out',
            'no_reason': '',
        }

        # Build all rows in memory first (no DB hits yet) — avoids holding
        # row locks open across a per-student query loop, which was causing
        # WORKER TIMEOUT under lock contention / slow round-trips on Render.
        student_data = []
        for student in students:
            status = request.POST.get(f'status_{student.pk}', 'A')
            remarks = ''
            if status == 'A':
                reason = request.POST.get(f'reason_{student.pk}', 'no_reason')
                if reason == 'other':
                    remarks = request.POST.get(f'custom_reason_{student.pk}', '').strip()[:100]
                else:
                    remarks = _reason_labels.get(reason, '')
            student_data.append((student, status, remarks))

        with transaction.atomic():
            # One query to find which rows already exist for this section+date
            existing = {
                a.student_id: a
                for a in Attendance.objects.filter(section=section, date=selected_date)
            }

            # Track which students were ALREADY marked absent before this save
            already_absent_ids = {
                s_id for s_id, row in existing.items() if row.status == 'A'
            }

            to_create = []
            to_update = []
            for student, status, remarks in student_data:
                existing_row = existing.get(student.pk)
                if existing_row:
                    existing_row.status = status
                    existing_row.remarks = remarks
                    to_update.append(existing_row)
                else:
                    to_create.append(Attendance(
                        student=student, date=selected_date,
                        section=section, status=status, remarks=remarks,
                    ))

            if to_create:
                Attendance.objects.bulk_create(to_create)
            if to_update:
                Attendance.objects.bulk_update(to_update, ['status', 'remarks'])

        # --- Queue WhatsApp alerts for newly absent students ---
        from django.conf import settings as conf

        queued_count = 0

        for student, status, remarks in student_data:
            if status == 'A':
                # Skip if student was already marked 'A' in an earlier save today
                if student.pk in already_absent_ids:
                    continue

                parent_phone = (student.mobile or student.second_mobile or '').strip()
                if not parent_phone:
                    continue

                PendingMessage.objects.create(
                    student=student,
                    phone=parent_phone,
                    message_type=PendingMessage.TYPE_TEMPLATE,
                    template_name=getattr(conf, 'META_TEMPLATE_ABSENCE', 'absence_alert'),
                    template_params=[student.name, selected_date.strftime('%d-%m-%Y'), remarks or "Absent"],
                    language='en',
                    status=PendingMessage.STATUS_PENDING,
                )
                queued_count += 1

        # Construct user success message
        msg = f'Attendance saved for {section} on {selected_date}.'
        if queued_count > 0:
            msg += f' {queued_count} WhatsApp alert(s) queued for sending.'

        messages.success(request, msg)
        base_url = reverse('attendance_list')
        query_string = urlencode({'date': selected_date.isoformat(), 'section': section_id})
        return redirect(f"{base_url}?{query_string}")
    return redirect('attendance_list')


@admin_required
def attendance_send_whatsapp(request):
    """Send WhatsApp messages to all absent students' parents for a given section+date."""
    from django.http import JsonResponse
    from whatsapp.services import send_absence_alert

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST only'}, status=405)

    section_id = request.POST.get('section_id')
    date_str = request.POST.get('date')
    target_lang = (request.POST.get('language') or request.GET.get('language') or 'en').lower().strip()

    if not section_id or not date_str:
        return JsonResponse({'success': False, 'error': 'section_id and date are required'}, status=400)

    if not _section_allowed(request.user, section_id):
        return JsonResponse({'success': False, 'error': 'You do not have access to that section.'}, status=403)

    section = get_object_or_404(Section, pk=section_id)
    att_date = parse_date_input(date_str)
    if not att_date:
        return JsonResponse({'success': False, 'error': f'Invalid date: {date_str!r}'}, status=400)

    absent_records = Attendance.objects.filter(
        section=section, date=att_date, status='A'
    ).select_related('student')

    if not absent_records.exists():
        return JsonResponse({'success': True, 'results': [], 'message': 'No absent students found.'})

    results = []
    for record in absent_records:
        student = record.student
        parent_phone = (student.mobile or student.second_mobile or '').strip()
        if not parent_phone:
            results.append({'name': student.name, 'status': 'no_phone'})
            continue

        result = send_absence_alert(
            student_name=student.name,
            parent_phone=parent_phone,
            date_str=att_date.strftime('%d-%m-%Y'),
            section=str(section),
            reason=getattr(record, 'reason', '') or "Absent",
            language=target_lang,
        )

        if result['success']:
            results.append({'name': student.name, 'phone': parent_phone, 'status': 'sent'})
        else:
            results.append({'name': student.name, 'phone': parent_phone, 'status': 'failed', 'error': result.get('error', '')})

    return JsonResponse({'success': True, 'results': results})


@all_roles_required
def attendance_save_reasons(request):
    """Save absence reasons for already-marked absent students, then send WhatsApp to parents."""
    from django.http import JsonResponse
    from whatsapp.services import send_absence_alert

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST only'}, status=405)

    section_id = request.POST.get('section_id')
    date_str = request.POST.get('date')

    if not _section_allowed(request.user, section_id):
        return JsonResponse({'success': False, 'error': 'You do not have access to that section.'}, status=403)

    section = get_object_or_404(Section, pk=section_id)
    att_date = parse_date_input(date_str)
    if not att_date:
        return JsonResponse({'success': False, 'error': 'Invalid date'}, status=400)

    _reason_labels = {'health': 'Health Issue', 'went_out': 'Went Out', 'no_reason': ''}

    absent_records = list(
        Attendance.objects.filter(section=section, date=att_date, status='A').select_related('student')
    )

    for record in absent_records:
        pk = record.student_id
        reason = request.POST.get(f'reason_{pk}', 'no_reason')
        if reason == 'other':
            remarks = request.POST.get(f'custom_reason_{pk}', '').strip()[:100]
        else:
            remarks = _reason_labels.get(reason, '')
        record.remarks = remarks
        record.save(update_fields=['remarks'])

    if request.POST.get('save_only') == '1':
        return JsonResponse({'success': True, 'message': 'Reasons saved.'})

    results = []
    for record in absent_records:
        student = record.student
        parent_phone = (student.mobile or student.second_mobile or '').strip()
        if not parent_phone:
            results.append({'name': student.name, 'status': 'no_phone'})
            continue

        result = send_absence_alert(
            student_name=student.name,
            parent_phone=parent_phone,
            date_str=att_date.strftime('%d-%m-%Y'),
            section=str(section),
            reason=record.remarks or '',
        )

        if result['success']:
            results.append({'name': student.name, 'phone': parent_phone, 'status': 'sent'})
        else:
            results.append({'name': student.name, 'phone': parent_phone, 'status': 'failed', 'error': result.get('error', '')})

    return JsonResponse({'success': True, 'results': results})


@all_roles_required
def attendance_report(request):
    section_id = request.GET.get('section', '')
    today = timezone.localdate()

    try:
        month = int(request.GET.get('month', today.month))
        year_val = int(request.GET.get('year', today.year))
        if not (1 <= month <= 12):
            month = today.month
    except (ValueError, TypeError):
        month = today.month
        year_val = today.year

    sections = _get_faculty_sections(request.user)
    report_data = []
    selected_section = None

    if section_id and str(section_id).isdigit():
        # --- Section restriction ---
        if not _section_allowed(request.user, section_id):
            messages.error(request, 'You do not have access to that section.')
            return redirect('attendance_report')
        selected_section = get_object_or_404(Section, pk=section_id)
        # Use correct related_name: attendance_records
        students = Student.objects.filter(section=selected_section, is_active=True).annotate(
            present_count=Count('attendance_records', filter=Q(
                attendance_records__date__month=month,
                attendance_records__date__year=year_val,
                attendance_records__status='P')),
            absent_count=Count('attendance_records', filter=Q(
                attendance_records__date__month=month,
                attendance_records__date__year=year_val,
                attendance_records__status='A')),
        )
        for student in students:
            total = student.present_count + student.absent_count
            pct = round((student.present_count / total * 100), 1) if total > 0 else 0
            report_data.append({
                'student': student, 'present': student.present_count,
                'absent': student.absent_count,
                'total': total, 'percentage': pct
            })

    return render(request, 'attendance/report.html', {
        'sections': sections, 'report_data': report_data,
        'selected_section': selected_section, 'section_id': str(section_id),
        'month': str(month), 'year': str(year_val),
        'months': [(str(i), m) for i, m in enumerate(
            ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], 1)],
        'years': [str(y) for y in range(2023, 2028)],
    })


@all_roles_required
def attendance_yearly(request):
    section_id = request.GET.get('section', '')
    year_val = request.GET.get('year', str(timezone.localdate().year))
    sections = _get_faculty_sections(request.user)
    report_data = []
    selected_section = None
    month_names = ['Jun','Jul','Aug','Sep','Oct','Nov','Dec','Jan','Feb','Mar','Apr','May']
    month_nums =  [6,    7,    8,    9,    10,   11,   12,   1,    2,    3,    4,    5]

    if section_id and str(section_id).isdigit():
        # --- Section restriction ---
        if not _section_allowed(request.user, section_id):
            messages.error(request, 'You do not have access to that section.')
            return redirect('attendance_yearly')
        selected_section = get_object_or_404(Section, pk=section_id)
        yr = int(year_val)
        students = Student.objects.filter(section=selected_section, is_active=True)
        records = Attendance.objects.filter(
            student__in=students,
            date__gte=f"{yr}-06-01",
            date__lte=f"{yr+1}-05-31"
        ).order_by('date')
        att_map = {}
        # Day-level records per student per month, for the expandable view.
        day_map = {}
        for r in records:
            att_map.setdefault(r.student_id, {}).setdefault(r.date.month, []).append(r.status)
            day_map.setdefault(r.student_id, {}).setdefault(r.date.month, []).append({
                'date': r.date, 'status': r.status, 'remarks': r.remarks,
            })

        for student in students:
            s_map = att_map.get(student.pk, {})
            s_days = day_map.get(student.pk, {})
            monthly = []
            total_present = 0
            total_days = 0
            for mnum, mname in zip(month_nums, month_names):
                statuses = s_map.get(mnum, [])
                p = statuses.count('P')
                total = len(statuses)
                total_present += p
                total_days += total
                pct = round(p / total * 100) if total > 0 else None
                day_records = sorted(s_days.get(mnum, []), key=lambda d: d['date'])
                monthly.append({
                    'month_num': mnum, 'month_name': mname,
                    'present': p, 'total': total, 'pct': pct,
                    'days': day_records,
                })
            overall = round(total_present / total_days * 100, 1) if total_days > 0 else 0
            report_data.append({
                'student': student, 'monthly': monthly,
                'total_present': total_present, 'total_days': total_days, 'overall': overall,
            })

    return render(request, 'attendance/yearly.html', {
        'sections': sections, 'report_data': report_data,
        'selected_section': selected_section, 'section_id': str(section_id),
        'year_val': year_val, 'years': [str(y) for y in range(2023, 2028)],
        'month_names': month_names,
    })


@all_roles_required
def attendance_yearly_export_excel(request):
    """Export the yearly attendance report (per-month present/total) to Excel."""
    import openpyxl

    section_id = request.GET.get('section', '')
    year_val = request.GET.get('year', str(timezone.localdate().year))

    if not section_id or not str(section_id).isdigit():
        messages.error(request, 'Please select a section before exporting.')
        return redirect('attendance_yearly')

    # --- Section restriction ---
    if not _section_allowed(request.user, section_id):
        messages.error(request, 'You do not have access to that section.')
        return redirect('attendance_yearly')

    selected_section = get_object_or_404(Section, pk=section_id)
    yr = int(year_val)
    students = Student.objects.filter(section=selected_section, is_active=True)
    records = Attendance.objects.filter(
        student__in=students,
        date__gte=f"{yr}-06-01",
        date__lte=f"{yr+1}-05-31"
    )
    month_names = ['Jun','Jul','Aug','Sep','Oct','Nov','Dec','Jan','Feb','Mar','Apr','May']
    month_nums =  [6,    7,    8,    9,    10,   11,   12,   1,    2,    3,    4,    5]

    att_map = {}
    for r in records:
        att_map.setdefault(r.student_id, {}).setdefault(r.date.month, []).append(r.status)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Yearly Attendance"

    headers = ['#', 'Admission No', 'Name'] + month_names + ['Total Present', 'Total Days', 'Overall %']
    for i, h in enumerate(headers, 1):
        ws.cell(1, i, h)

    for idx, student in enumerate(students, 1):
        s_map = att_map.get(student.pk, {})
        row = idx + 1
        ws.cell(row, 1, idx)
        ws.cell(row, 2, student.admission_number)
        ws.cell(row, 3, student.name)
        total_present = 0
        total_days = 0
        for j, mnum in enumerate(month_nums):
            statuses = s_map.get(mnum, [])
            p = statuses.count('P')
            total = len(statuses)
            total_present += p
            total_days += total
            ws.cell(row, 4 + j, f"{p}/{total}" if total else '-')
        col = 4 + len(month_nums)
        ws.cell(row, col, total_present)
        ws.cell(row, col + 1, total_days)
        ws.cell(row, col + 2, round(total_present / total_days * 100, 1) if total_days else 0)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    filename = f"attendance_{selected_section}_{year_val}.xlsx".replace(' ', '_')
    response['Content-Disposition'] = f'attachment; filename={filename}'
    wb.save(response)
    return response


@all_roles_required
def attendance_report_export(request):
    """Export attendance report (monthly) filtered by section/month/year to PDF or Excel."""
    from django.http import HttpResponse
    import io

    section_id = request.GET.get('section', '')
    month      = int(request.GET.get('month', timezone.localdate().month))
    year_val   = int(request.GET.get('year', timezone.localdate().year))
    fmt        = request.GET.get('fmt', 'pdf')

    if not section_id:
        messages.error(request, 'Please select a section.')
        return redirect('attendance_report')

    # --- Section restriction ---
    if not _section_allowed(request.user, section_id):
        messages.error(request, 'You do not have access to that section.')
        return redirect('attendance_report')

    selected_section = get_object_or_404(Section, pk=section_id)
    students = Student.objects.filter(section=selected_section, is_active=True).annotate(
        present_count=Count('attendance_records', filter=Q(
            attendance_records__date__month=month,
            attendance_records__date__year=year_val,
            attendance_records__status='P')),
        absent_count=Count('attendance_records', filter=Q(
            attendance_records__date__month=month,
            attendance_records__date__year=year_val,
            attendance_records__status='A')),
    )

    rows = []
    for student in students:
        total = student.present_count + student.absent_count
        pct   = round(student.present_count / total * 100, 1) if total else 0
        rows.append({
            'name':    student.name,
            'present': student.present_count,
            'absent':  student.absent_count,
            'total':   total,
            'pct':     pct,
        })

    month_name = ['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][month]
    title = f"Attendance Report — {selected_section} — {month_name} {year_val}"

    if fmt == 'excel':
        return _att_export_excel(rows, title)
    return _att_export_pdf(rows, title)


def _att_export_excel(rows, title):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance"

    BLUE  = PatternFill("solid", fgColor="1A47A8")
    GREEN = PatternFill("solid", fgColor="DCFCE7")
    RED   = PatternFill("solid", fgColor="FEE2E2")
    thin  = Border(left=Side(style='thin'), right=Side(style='thin'),
                   top=Side(style='thin'), bottom=Side(style='thin'))

    ws.merge_cells('A1:F1')
    ws['A1'] = title
    ws['A1'].font = Font(bold=True, size=12, color="1A47A8")
    ws['A1'].alignment = Alignment(horizontal='center')

    headers = ['#', 'Student Name', 'Present', 'Absent', 'Total Days', '%']
    widths  = [6, 35, 12, 12, 14, 10]
    for i, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(2, i, h)
        c.fill = BLUE
        c.font = Font(bold=True, color="FFFFFF")
        c.alignment = Alignment(horizontal='center')
        c.border = thin
        ws.column_dimensions[c.column_letter].width = w

    for idx, row in enumerate(rows, 1):
        r = idx + 2
        vals = [idx, row['name'], row['present'], row['absent'], row['total'], f"{row['pct']}%"]
        for col, val in enumerate(vals, 1):
            c = ws.cell(r, col, val)
            c.border = thin
            c.alignment = Alignment(horizontal='center' if col != 2 else 'left')
            if col == 3:   c.fill = GREEN
            elif col == 4: c.fill = RED

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=attendance_report.xlsx'
    wb.save(response)
    return response


def _att_export_pdf(rows, title):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from django.http import HttpResponse
    import io

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=12*mm, bottomMargin=12*mm)
    DARK_BLUE = colors.HexColor("#1A47A8")
    GREEN     = colors.HexColor("#DCFCE7")
    RED       = colors.HexColor("#FEE2E2")
    LGREY     = colors.HexColor("#EAF1FB")

    story = [Paragraph(title, ParagraphStyle('t', fontSize=12, fontName='Helvetica-Bold',
                                              textColor=DARK_BLUE, alignment=1, spaceAfter=8))]
    headers = ['#', 'Student Name', 'Present', 'Absent', 'Total', '%']
    data = [headers]
    for i, row in enumerate(rows, 1):
        data.append([str(i), row['name'], str(row['present']), str(row['absent']),
                     str(row['total']), f"{row['pct']}%"])

    col_w = [10*mm, 70*mm, 22*mm, 22*mm, 22*mm, 18*mm]
    n = len(rows)
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), DARK_BLUE),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0,0), (-1,-1), 8),
        ('ROWBACKGROUNDS', (0,1), (-1,n), [colors.white, LGREY]),
        ('BACKGROUND', (2,1), (2,n), GREEN),
        ('BACKGROUND', (3,1), (3,n), RED),
        ('ALIGN',      (0,0), (-1,-1), 'CENTER'),
        ('ALIGN',      (1,0), (1,-1), 'LEFT'),
        ('GRID',       (0,0), (-1,-1), 0.3, colors.HexColor("#D1D5DB")),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t)
    doc.build(story)
    buf.seek(0)
    response = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename=attendance_report.pdf'
    return response


# ---------------------------------------------------------------------------
# Quick Attendance & WhatsApp Prototype Views
# ---------------------------------------------------------------------------

def quick_login_view(request):
    """
    Time-window-gated quick login page for attendance marking.
    """
    if request.user.is_authenticated:
        is_open, msg = AttendanceWindow.is_currently_open(request.user)
        if is_open:
            return redirect('attendance_tap_sections')
        else:
            return redirect('attendance_window_closed')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            if not user.is_active:
                messages.error(request, "Your account is disabled.")
            elif getattr(user, 'is_blocked_by_admin', False):
                messages.error(request, f"Account blocked: {user.blocked_reason or 'Contact Administrator.'}")
            else:
                login(request, user)
                is_open, msg = AttendanceWindow.is_currently_open(user)
                if is_open:
                    return redirect('attendance_tap_sections')
                else:
                    return redirect('attendance_window_closed')
        else:
            messages.error(request, "Invalid username or password.")

    is_open, window_msg = AttendanceWindow.is_currently_open()
    config = AttendanceWindow.objects.filter(is_active=True).first()
    start_fmt = config.start_time.strftime("%I:%M %p") if config and config.start_time else "08:00 AM"
    end_fmt = config.end_time.strftime("%I:%M %p") if config and config.end_time else "09:00 AM"

    return render(request, 'attendance/quick_login.html', {
        'is_open': is_open,
        'window_msg': window_msg,
        'start_time': start_fmt,
        'end_time': end_fmt,
        'server_time': timezone.localtime(),
    })


def window_closed_view(request):
    """
    Screen shown when attendance window is closed for faculty.
    """
    config = AttendanceWindow.objects.filter(is_active=True).first()
    start_fmt = config.start_time.strftime("%I:%M %p") if config and config.start_time else "08:00 AM"
    end_fmt = config.end_time.strftime("%I:%M %p") if config and config.end_time else "09:00 AM"
    return render(request, 'attendance/window_closed.html', {
        'start_time': start_fmt,
        'end_time': end_fmt,
        'server_time': timezone.localtime(),
        'user': request.user,
    })


@all_roles_required
def tap_attendance_sections(request):
    """
    Section selection screen for quick tap attendance.
    """
    is_open, msg = AttendanceWindow.is_currently_open(request.user)
    if not is_open:
        return redirect('attendance_window_closed')

    date_str = request.GET.get('date', '')
    today = timezone.localdate()
    selected_date = parse_date_input(date_str, default=today)

    sections = _get_faculty_sections(request.user)

    pending_sections = []
    completed_sections = []

    for s in sections:
        total_students = Student.objects.filter(section=s, is_active=True).count()
        marked_count = Attendance.objects.filter(section=s, date=selected_date).count()
        item = {
            'section': s,
            'total_students': total_students,
            'marked_count': marked_count,
            'is_completed': marked_count >= total_students and total_students > 0,
        }
        if item['is_completed']:
            completed_sections.append(item)
        else:
            pending_sections.append(item)

    return render(request, 'attendance/tap_sections.html', {
        'sections': pending_sections + completed_sections,
        'pending_sections': pending_sections,
        'completed_sections': completed_sections,
        'selected_date': selected_date,
        'today': today,
        'server_time': timezone.localtime(),
    })



@all_roles_required
def tap_attendance_view(request, section_id):
    """
    Tap attendance marking view showing large student cards.
    """
    is_open, msg = AttendanceWindow.is_currently_open(request.user)
    if not is_open:
        return redirect('attendance_window_closed')

    if not _section_allowed(request.user, section_id):
        messages.error(request, "You do not have access to this section.")
        return redirect('attendance_tap_sections')

    date_str = request.GET.get('date', '')
    today = timezone.localdate()
    selected_date = parse_date_input(date_str, default=today)

    section = get_object_or_404(Section, pk=section_id)

    students = Student.objects.filter(section=section, is_active=True).order_by('name')
    existing_attendance = Attendance.objects.filter(section=section, date=selected_date)
    attendance_map = {a.student_id: a.status for a in existing_attendance}

    students_list = []
    for s in students:
        phone = (s.mobile or s.second_mobile or '').strip()
        students_list.append({
            'id': s.id,
            'name': s.name,
            'roll_number': getattr(s, 'hall_ticket_number', '') or s.admission_number,
            'admission_number': s.admission_number,
            'photo': s.photo.url if getattr(s, 'photo', None) and s.photo else None,
            'phone': phone,
            'status': attendance_map.get(s.id, None),
        })

    is_admin_user = (request.user.is_superuser or getattr(request.user, 'role', '') in ['admin', 'accounts'])
    has_existing = existing_attendance.exists()
    is_locked = has_existing and not is_admin_user

    return render(request, 'attendance/tap_section.html', {
        'section': section,
        'selected_date': selected_date,
        'today': today,
        'is_admin_user': is_admin_user,
        'is_locked': is_locked,
        'has_existing': has_existing,
        'students_json': json.dumps(students_list),
        'students': students_list,
        'total_count': len(students_list),
        'marked_count': len(attendance_map),
        'present_count': sum(1 for status in attendance_map.values() if status == 'P'),
        'absent_count': sum(1 for status in attendance_map.values() if status == 'A'),
    })



@all_roles_required
def tap_mark_api(request):
    """
    AJAX API endpoint for instant student attendance tap marking.
    Creates Attendance record and enqueues a PendingMessage synchronously for Present status.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    is_open, msg = AttendanceWindow.is_currently_open(request.user)
    if not is_open:
        return JsonResponse({'success': False, 'error': msg}, status=403)

    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST

        student_id = data.get('student_id')
        section_id = data.get('section_id')
        status = data.get('status', 'P')  # 'P' for Present, 'A' for Absent
        date_str = data.get('date', '')

        if not student_id or not section_id:
            return JsonResponse({'success': False, 'error': 'student_id and section_id required'}, status=400)

        if not _section_allowed(request.user, section_id):
            return JsonResponse({'success': False, 'error': 'Access denied to section'}, status=403)

        student = get_object_or_404(Student, pk=student_id)
        section = get_object_or_404(Section, pk=section_id)
        today = timezone.localdate()
        selected_date = parse_date_input(date_str, default=today)

        # Time/Lock enforcement: Faculty cannot overwrite submitted attendance
        if request.user.role == 'faculty' and Attendance.objects.filter(section=section, date=selected_date).exists():
            return JsonResponse({
                'success': False,
                'error': f'Attendance for {section} on {selected_date.strftime("%d-%m-%Y")} is submitted and locked.'
            }, status=403)

        # 1. Update/Create Attendance record (Faculty/Admin marking)
        att_record, created = Attendance.objects.update_or_create(
            student=student,
            date=selected_date,
            defaults={
                'status': status,
                'section': section,
            }
        )

        return JsonResponse({
            'success': True,
            'student_id': student.id,
            'status': status,
            'date': selected_date.isoformat(),
        })


    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@all_roles_required
def attendance_review(request):
    """
    Admin review page showing today's attendance and WhatsApp message status per section.
    Accessible anytime by admin/accounts (and faculty).
    """
    date_str = request.GET.get('date', '')
    section_id = request.GET.get('section', '')

    today = timezone.localdate()
    selected_date = parse_date_input(date_str, default=today)

    sections = _get_faculty_sections(request.user)
    selected_section = None
    records_data = []
    stats = {'total': 0, 'present': 0, 'absent': 0, 'unmarked': 0, 'msg_pending': 0, 'msg_sent': 0, 'msg_failed': 0}

    if section_id and str(section_id).isdigit():
        if not _section_allowed(request.user, section_id):
            messages.error(request, 'You do not have access to that section.')
            return redirect('attendance_review')
        selected_section = get_object_or_404(Section, pk=section_id)
        students = Student.objects.filter(section=selected_section, is_active=True).order_by('name')

        att_map = {a.student_id: a for a in Attendance.objects.filter(section=selected_section, date=selected_date)}

        msgs = PendingMessage.objects.filter(
            student__in=students,
            created_at__date=selected_date
        ).order_by('-created_at')

        msg_map = {}
        for m in msgs:
            if m.student_id not in msg_map:
                msg_map[m.student_id] = m

        for s in students:
            att = att_map.get(s.id)
            status = att.status if att else 'N'
            msg_obj = msg_map.get(s.id)

            records_data.append({
                'student': s,
                'attendance': att,
                'status': status,
                'message': msg_obj,
            })

            stats['total'] += 1
            if status == 'P':
                stats['present'] += 1
            elif status == 'A':
                stats['absent'] += 1
            else:
                stats['unmarked'] += 1

            if msg_obj:
                if msg_obj.status == 'pending':
                    stats['msg_pending'] += 1
                elif msg_obj.status == 'sent':
                    stats['msg_sent'] += 1
                elif msg_obj.status == 'failed':
                    stats['msg_failed'] += 1

    # Count failed WhatsApp messages today across all sections/faculty for alerting banner
    failed_today_count = PendingMessage.objects.filter(
        status=PendingMessage.STATUS_FAILED,
        updated_at__date=selected_date
    ).count()

    return render(request, 'attendance/review.html', {
        'sections': sections,
        'selected_section': selected_section,
        'section_id': str(section_id),
        'selected_date': selected_date,
        'today': today,
        'records': records_data,
        'stats': stats,
        'failed_today_count': failed_today_count,
        'dynamic_list': records_data,
    })


import threading
from django.core.management import call_command


def trigger_whatsapp_sender_in_background(headless=True, batch_size=None):
    """Messages are stored in DB (PendingMessage) and processed by the scheduled Render Cron Job."""
    pass


@admin_required
def trigger_whatsapp_sender_view(request):
    """
    Admin UI view ("Dispatch WhatsApp Messages Now" / "Retry Dispatch" button).
    Signals background Cron Job to process messages by resetting failed messages to 'pending'.
    Reflects the daily fixed dispatch schedule (10:30 AM).
    """
    if request.method == 'POST':
        today = timezone.localdate()
        reset_count = PendingMessage.objects.filter(
            status=PendingMessage.STATUS_FAILED,
            updated_at__date=today
        ).update(status=PendingMessage.STATUS_PENDING, error_message='')

        pending_count = PendingMessage.objects.filter(status=PendingMessage.STATUS_PENDING).count()
        dispatch_time = getattr(settings, 'WHATSAPP_DAILY_DISPATCH_TIME', '10:30')

        if pending_count > 0 or reset_count > 0:
            from whatsapp.services import dispatch_pending_messages_async
            dispatch_pending_messages_async()

        if reset_count > 0:
            messages.success(request, f"Re-queued and dispatched {reset_count} failed message(s).")
        elif pending_count > 0:
            messages.info(request, f"Triggered immediate dispatch for {pending_count} pending message(s). Scheduled daily auto-dispatch is at {dispatch_time} AM.")
        else:
            messages.info(request, f"No pending or failed messages. Scheduled daily auto-dispatch is at {dispatch_time} AM.")

        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        return redirect('attendance_review')
    return JsonResponse({'success': False, 'error': 'POST required'}, status=405)


@admin_required
def enqueue_section_absent_whatsapp(request):
    """
    Enqueues PendingMessage rows for all students marked ABSENT ('A') in a section today (or selected date).
    Can be called via AJAX or standard POST form submit. Triggers instant async dispatch.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    section_id = request.POST.get('section_id') or request.GET.get('section_id')
    if not section_id and request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
            section_id = data.get('section_id')
        except Exception:
            pass

    if not section_id or not str(section_id).isdigit():
        messages.error(request, "Invalid section ID.")
        return redirect('attendance_tap_sections')

    if not _section_allowed(request.user, section_id):
        messages.error(request, "You do not have access to this section.")
        return redirect('attendance_tap_sections')

    section = get_object_or_404(Section, pk=section_id)
    date_str = request.POST.get('date', '') or request.GET.get('date', '')
    target_lang = (request.POST.get('language') or request.GET.get('language') or 'en').lower().strip()
    today = timezone.localdate()
    selected_date = parse_date_input(date_str, default=today)

    absent_records = Attendance.objects.filter(
        section=section,
        date=selected_date,
        status='A'
    ).select_related('student')

    total_absent = absent_records.count()
    already_queued_count = 0
    enqueued_count = 0
    template_name = getattr(settings, 'META_TEMPLATE_ABSENCE', 'absence_alert')

    for record in absent_records:
        student = record.student
        already_exists = PendingMessage.objects.filter(
            student=student,
            created_at__date=selected_date,
        ).exclude(status=PendingMessage.STATUS_FAILED).exists()

        if already_exists:
            already_queued_count += 1
        else:
            phone = (student.mobile or student.second_mobile or '').strip()
            msg_text = (
                f"Dear {student.name}, You were marked ABSENT on "
                f"{selected_date.strftime('%d-%m-%Y')} for {section}. "
                f"Please contact college. - Sri NRI Junior College"
            )
            template_params = [
                student.name,
                selected_date.strftime('%d-%m-%Y'),
                "Absent Alert",
            ]
            PendingMessage.objects.create(
                student=student,
                phone=phone,
                message_type=PendingMessage.TYPE_TEMPLATE,
                template_name=template_name,
                template_params=template_params,
                language=target_lang,
                message=msg_text,
                status=PendingMessage.STATUS_PENDING
            )
            enqueued_count += 1

    if enqueued_count > 0:
        from whatsapp.services import dispatch_pending_messages_async
        dispatch_pending_messages_async()

    if total_absent == 0:
        msg_text = f"No absent students found in {section} on {selected_date.strftime('%d-%m-%Y')} (all marked Present or unmarked)."
    elif enqueued_count > 0:
        msg_text = f"Enqueued {enqueued_count} absent WhatsApp alert(s) for {section} on {selected_date.strftime('%d-%m-%Y')}."
    else:
        msg_text = f"All {already_queued_count} absent student(s) in {section} already have WhatsApp alerts queued or sent for {selected_date.strftime('%d-%m-%Y')}."

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({'success': True, 'enqueued_count': enqueued_count, 'message': msg_text})

    messages.success(request, msg_text)
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('attendance_review')
