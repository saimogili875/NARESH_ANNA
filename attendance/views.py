from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from datetime import date, datetime
from django.db import transaction
from django.db.models import Count, Q
from django.urls import reverse
from urllib.parse import urlencode
from .models import Attendance
from students.models import Student
from accounts.models import Section
from accounts.decorators import all_roles_required, admin_faculty_required


def _get_faculty_sections(user):
    """Return the queryset of sections this user is allowed to access.

    - Admin / superuser → all sections (unrestricted).
    - Faculty → only their assigned_sections.
    - Everyone else → empty queryset.
    """
    if user.is_superuser or user.role == 'admin':
        return Section.objects.select_related('group').all()
    if user.role == 'faculty':
        try:
            return user.faculty_profile.assigned_sections.select_related('group').all()
        except Exception:
            return Section.objects.none()
    return Section.objects.none()


def _section_allowed(user, section_id):
    """Check if a specific section_id is in the user's allowed set."""
    if user.is_superuser or user.role == 'admin':
        return True
    return _get_faculty_sections(user).filter(pk=section_id).exists()


@all_roles_required
def attendance_list(request):
    today = timezone.localdate()
    date_str = request.GET.get('date', '')
    section_id = request.GET.get('section', '')

    try:
        selected_date = date.fromisoformat(date_str) if date_str else today
    except ValueError:
        selected_date = today

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
                messages.error(
                    request,
                    f'Attendance marking is locked after {cutoff_h}:{cutoff_m:02d} AM. Please contact admin.'
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

        try:
            selected_date = date.fromisoformat(date_str)
        except (ValueError, TypeError):
            try:
                selected_date = datetime.strptime(date_str, "%B %d, %Y").date()
            except (ValueError, TypeError):
                messages.error(request, "Invalid date format.")
                return redirect('attendance_list')

        students = Student.objects.filter(section=section, is_active=True)

        # Lock check — block edits if attendance already saved
        if Attendance.objects.filter(student__in=students, date=selected_date).exists():
            messages.error(request, f'Attendance already saved for {section} on {selected_date}. Changes are not allowed.')
            base_url = reverse('attendance_list')
            query_string = urlencode({'date': selected_date.isoformat(), 'section': section_id})
            return redirect(f"{base_url}?{query_string}")

        _reason_labels = {
            'health': 'Health Issue',
            'went_out': 'Went Out',
            'no_reason': '',
        }
        with transaction.atomic():
            for student in students:
                status = request.POST.get(f'status_{student.pk}', 'A')
                remarks = ''
                if status == 'A':
                    reason = request.POST.get(f'reason_{student.pk}', 'no_reason')
                    if reason == 'other':
                        remarks = request.POST.get(f'custom_reason_{student.pk}', '').strip()[:100]
                    else:
                        remarks = _reason_labels.get(reason, '')
                Attendance.objects.create(
                    student=student, date=selected_date,
                    status=status, section=section, remarks=remarks,
                )
        messages.success(request, f'Attendance saved for {section} on {selected_date}.')
        base_url = reverse('attendance_list')
        query_string = urlencode({'date': selected_date.isoformat(), 'section': section_id})
        return redirect(f"{base_url}?{query_string}")
    return redirect('attendance_list')


@all_roles_required
def attendance_send_whatsapp(request):
    """Send WhatsApp messages to all absent students for a given section+date."""
    from django.http import JsonResponse
    from django.conf import settings
    from twilio.rest import Client

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST only'}, status=405)

    section_id = request.POST.get('section_id')
    date_str = request.POST.get('date')

    if not section_id or not date_str:
        return JsonResponse({'success': False, 'error': 'section_id and date are required'}, status=400)

    # --- Section restriction ---
    if not _section_allowed(request.user, section_id):
        return JsonResponse({'success': False, 'error': 'You do not have access to that section.'}, status=403)

    section = get_object_or_404(Section, pk=section_id)
    try:
        att_date = datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': f'Invalid date: {date_str!r}'}, status=400)

    absent_records = Attendance.objects.filter(
        section=section, date=att_date, status='A'
    ).select_related('student')

    if not absent_records.exists():
        return JsonResponse({'success': True, 'results': [], 'message': 'No absent students found.'})

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Twilio init failed: {e}'}, status=500)

    results = []
    for record in absent_records:
        student = record.student
        phone = student.mobile.strip() if student.mobile else ''
        if not phone:
            results.append({'name': student.name, 'status': 'no_phone'})
            continue

        msg_body = (
            f"Dear {student.name}, You were marked ABSENT on "
            f"{att_date.strftime('%d-%m-%Y')} for {section}. "
            f"Please contact college. - Sri NRI Junior College"
        )

        try:
            client.messages.create(
                from_=settings.TWILIO_WHATSAPP_FROM,
                body=msg_body,
                to=f"whatsapp:+91{phone}",
            )
            results.append({'name': student.name, 'phone': phone, 'status': 'sent'})
        except Exception as e:
            results.append({'name': student.name, 'phone': phone, 'status': 'failed', 'error': str(e)})

    return JsonResponse({'success': True, 'results': results})


@all_roles_required
def attendance_save_reasons(request):
    """Save absence reasons for already-marked absent students, then send WhatsApp."""
    from django.http import JsonResponse
    from django.conf import settings
    from twilio.rest import Client

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST only'}, status=405)

    section_id = request.POST.get('section_id')
    date_str = request.POST.get('date')

    # --- Section restriction ---
    if not _section_allowed(request.user, section_id):
        return JsonResponse({'success': False, 'error': 'You do not have access to that section.'}, status=403)

    section = get_object_or_404(Section, pk=section_id)
    try:
        att_date = date.fromisoformat(date_str)
    except (ValueError, TypeError):
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

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Twilio init failed: {e}'}, status=500)

    results = []
    for record in absent_records:
        student = record.student
        phone = (student.mobile or '').strip()
        if not phone:
            results.append({'name': student.name, 'status': 'no_phone'})
            continue
        reason_text = record.remarks or 'No reason given'
        msg_body = (
            f"Dear {student.name}, You were marked ABSENT on "
            f"{att_date.strftime('%d-%m-%Y')} for {section}. "
            f"Reason: {reason_text}. "
            f"Please contact college. - Sri NRI Junior College"
        )
        try:
            client.messages.create(
                from_=settings.TWILIO_WHATSAPP_FROM,
                body=msg_body,
                to=f"whatsapp:+91{phone}",
            )
            results.append({'name': student.name, 'phone': phone, 'status': 'sent'})
        except Exception as e:
            results.append({'name': student.name, 'phone': phone, 'status': 'failed', 'error': str(e)})

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
