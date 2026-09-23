from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
import openpyxl
from openpyxl.utils import get_column_letter
from .models import Student
from .forms import StudentForm, StudentSearchForm
from accounts.models import Section, AcademicYear
from accounts.decorators import admin_required, admin_accounts_required, all_roles_required
from accounts.utils import _get_faculty_sections
from django.core.paginator import Paginator




@all_roles_required
def student_list(request):
    allowed_sections = _get_faculty_sections(request.user)
    students = Student.objects.filter(is_active=True, section__in=allowed_sections).select_related('section__group')
    group = request.GET.get('group')
    year = request.GET.get('year')
    section = request.GET.get('section')
    q = request.GET.get('q')

    if group:
        students = students.filter(section__group_id=group)
    if year:
        students = students.filter(section__year=year)
    if section:
        students = students.filter(section_id=section)
    if q:
        students = students.filter(
            Q(name__icontains=q) | Q(admission_number__icontains=q) |
            Q(hall_ticket_number__icontains=q) | Q(mobile__icontains=q) |
            Q(aadhaar__icontains=q)
        )

    paginator = Paginator(students, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    from accounts.models import Group
    context = {
        'students': page_obj,
        'page_obj': page_obj,
        'groups': Group.objects.all(),
        'sections': Section.objects.all(),
        'total': students.count(),
    }
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    if is_ajax:
        return render(request, 'students/_list_table.html', context)
    return render(request, 'students/list.html', context)



@admin_accounts_required
def student_add(request):
    form = StudentForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Student added successfully.')
        return redirect('student_list')
    return render(request, 'students/form.html', {'form': form, 'title': 'Add Student'})


@admin_accounts_required
def student_edit(request, pk):
    obj = get_object_or_404(Student, pk=pk)
    form = StudentForm(request.POST or None, request.FILES or None, instance=obj)
    if form.is_valid():
        form.save()
        messages.success(request, 'Student updated.')
        return redirect('student_list')
    return render(request, 'students/form.html', {'form': form, 'title': 'Edit Student', 'student': obj})


from django.views.decorators.http import require_POST


@admin_accounts_required
@require_POST
def student_delete(request, pk):
    obj = get_object_or_404(Student, pk=pk)
    obj.delete()
    messages.success(request, 'Student removed.')
    return redirect('student_list')


@admin_required
@require_POST
def student_bulk_delete(request):
    ids = request.POST.getlist('student_ids')
    count, _ = Student.objects.filter(pk__in=ids).delete()
    messages.success(request, f'{len(ids)} student(s) removed.')
    return redirect('student_list')


@admin_required
@require_POST
def student_bulk_transfer(request):
    ids = request.POST.getlist('student_ids')
    section_id = request.POST.get('section')
    if not section_id:
        messages.error(request, 'Please choose a Group/Year/Section to move students into.')
        return redirect('student_list')
    section = get_object_or_404(Section, pk=section_id)
    transferred_students = list(Student.objects.filter(pk__in=ids))
    for s in transferred_students:
        s.section = section
        s.save()
    messages.success(request, f'{len(transferred_students)} student(s) moved to {section}.')
    return redirect('student_list')


# Fields safe to edit directly from the Students table (tap a cell to edit,
# and the "Change Details" bulk-edit screen). Only admins can touch these
# (every view below is @admin_required).
INLINE_EDITABLE_FIELDS = {
    'admission_number', 'name', 'father_name', 'mother_name', 'hall_ticket_number',
    'mobile', 'second_mobile', 'third_mobile', 'fourth_mobile',
    'aadhaar', 'address',
}

BULK_EDIT_OPTIONAL_FIELDS = (
    'father_name', 'mother_name', 'hall_ticket_number',
    'mobile', 'second_mobile', 'third_mobile', 'fourth_mobile',
    'aadhaar', 'address',
)


@admin_required
def student_bulk_edit(request):
    """Open every selected student's details in editable boxes on one screen
    ('Change Details' bulk action), then save them all at once."""
    if request.method == 'POST':
        ids = request.POST.getlist('student_ids')
        students = Student.objects.filter(pk__in=ids)
        updated = 0
        skipped = []
        for student in students:
            pk = student.pk
            name_val = request.POST.get(f'name_{pk}', '').strip()
            adm_val = request.POST.get(f'admission_number_{pk}', '').strip()
            if not name_val:
                skipped.append(f'{student.admission_number} (name cannot be empty)')
                continue
            if not adm_val:
                skipped.append(f'{student.admission_number} (admission number cannot be empty)')
                continue
            if Student.objects.exclude(pk=pk).filter(admission_number=adm_val).exists():
                skipped.append(f'{student.admission_number} (admission number "{adm_val}" already used by another student)')
                continue
            student.name = name_val
            student.admission_number = adm_val
            for field in BULK_EDIT_OPTIONAL_FIELDS:
                key = f'{field}_{pk}'
                if key in request.POST:
                    setattr(student, field, request.POST.get(key, '').strip())
            student.save()
            updated += 1
        messages.success(request, f'{updated} student(s) updated.')
        if skipped:
            messages.warning(request, f"Skipped: {'; '.join(skipped)}")
        return redirect('student_list')

    ids_param = request.GET.get('ids', '')
    id_list = [i for i in ids_param.split(',') if i]
    students = Student.objects.filter(pk__in=id_list).select_related('section__group')
    if not students:
        messages.error(request, 'No students selected to edit.')
        return redirect('student_list')
    return render(request, 'students/bulk_edit.html', {'students': students})


def _validate_inline_field(student, field, value):
    """Shared validation for a single inline-edit field. Returns an error
    string, or None if the value is OK to save."""
    if field == 'name' and not value:
        return 'Name cannot be empty.'
    if field == 'admission_number':
        if not value:
            return 'Admission number cannot be empty.'
        if Student.objects.exclude(pk=student.pk).filter(admission_number=value).exists():
            return f'Admission number "{value}" is already used by another student.'
    return None


@admin_required
@require_POST
def student_inline_update(request, pk):
    field = request.POST.get('field')
    value = request.POST.get('value', '').strip()
    if field not in INLINE_EDITABLE_FIELDS:
        return JsonResponse({'ok': False, 'error': 'That field cannot be edited inline.'}, status=400)
    student = get_object_or_404(Student, pk=pk)
    error = _validate_inline_field(student, field, value)
    if error:
        return JsonResponse({'ok': False, 'error': error}, status=400)
    setattr(student, field, value)
    try:
        student.save(update_fields=[field])
    except Exception as e:
        import logging
        logging.getLogger('django').error(f"Error updating student {pk} field {field}: {e}", exc_info=True)
        return JsonResponse({'ok': False, 'error': 'Unable to update student.'}, status=400)
    return JsonResponse({'ok': True, 'value': value})


@admin_required
@require_POST
def student_inline_bulk_save(request):
    """Save a batch of staged table-cell edits at once (the 'Save Changes'
    button that appears once you've tapped one or more cells)."""
    import json
    from django.db import transaction
    try:
        edits = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid request.'}, status=400)

    valid_pks = set()
    for e in edits:
        raw_pk = e.get('pk')
        if raw_pk and str(raw_pk).isdigit():
            valid_pks.add(int(raw_pk))

    students_map = {
        s.pk: s for s in Student.objects.select_related('section', 'academic_year').filter(pk__in=valid_pks)
    }

    results = []
    with transaction.atomic():
        for edit in edits:
            pk_raw = edit.get('pk')
            pk_int = int(pk_raw) if (pk_raw and str(pk_raw).isdigit()) else None
            field = edit.get('field')
            value = str(edit.get('value', '')).strip()
            key = f'{pk_raw}_{field}'

            if field not in INLINE_EDITABLE_FIELDS:
                results.append({'key': key, 'ok': False, 'error': 'That field cannot be edited inline.'})
                continue
            student = students_map.get(pk_int) if pk_int else None
            if not student:
                results.append({'key': key, 'ok': False, 'error': 'Student not found.'})
                continue
            error = _validate_inline_field(student, field, value)
            if error:
                results.append({'key': key, 'ok': False, 'error': error})
                continue
            setattr(student, field, value)
            try:
                student.save(update_fields=[field])
                results.append({'key': key, 'ok': True, 'value': value})
            except Exception as e:
                results.append({'key': key, 'ok': False, 'error': str(e)})

    return JsonResponse({'results': results})


@all_roles_required
def student_profile(request, pk):
    from marks.views import get_subjects_for_exam, get_subject_max_marks

    allowed_sections = _get_faculty_sections(request.user)
    student = get_object_or_404(Student.objects.filter(section__in=allowed_sections), pk=pk)
    attendance = student.attendance_records.all().order_by('-date')
    marks = student.marks.select_related('exam').order_by('-exam__date')
    fees = student.fees.prefetch_related('payments').first()

    # Pivot marks into one row per exam, subjects as left-to-right columns,
    # so the marks tab reads naturally for IPE / MPIC / BPIC / MEC / CEC.
    exams_map = {}
    for m in marks:
        entry = exams_map.setdefault(m.exam_id, {'exam': m.exam, 'marks': {}})
        entry['marks'][m.subject] = m

    exam_rows = []
    for entry in sorted(exams_map.values(), key=lambda e: e['exam'].date, reverse=True):
        exam = entry['exam']
        subjects = get_subjects_for_exam(exam)
        subject_max_marks = get_subject_max_marks(exam, subjects)
        row_marks = []
        total_obtained = 0
        total_max = 0
        for sub in subjects:
            m = entry['marks'].get(sub)
            max_val = subject_max_marks.get(sub, exam.max_marks)
            total_max += max_val
            if m:
                is_abs = m.is_absent
                if not is_abs and m.marks_obtained is not None:
                    total_obtained += float(m.marks_obtained)
            row_marks.append({'subject': sub, 'mark': m, 'max': max_val})
        exam_rows.append({
            'exam': exam, 'subject_marks': row_marks,
            'total_obtained': total_obtained, 'total_max': total_max,
        })


    return render(request, 'students/profile.html', {
        'student': student,
        'attendance': attendance,
        'marks': marks,
        'exam_rows': exam_rows,
        'fees': fees,
    })


@admin_required
def student_transfer(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        section_id = request.POST.get('section')
        student.section = get_object_or_404(Section, pk=section_id)
        student.save()
        messages.success(request, f'{student.name} transferred successfully.')
        return redirect('student_profile', pk=pk)
    sections = Section.objects.all()
    return render(request, 'students/transfer.html', {'student': student, 'sections': sections})


@admin_required
def student_promote(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        if student.section and student.section.year == '1':
            year2_section = Section.objects.filter(
                group=student.section.group, year='2', name=student.section.name
            ).first()
            if year2_section:
                student.section = year2_section
                student.save()
                messages.success(request, f'{student.name} promoted to 2nd Year.')
            else:
                messages.error(request, 'No matching 2nd year section found.')
        else:
            messages.warning(request, 'Student is already in 2nd year.')
        return redirect('student_profile', pk=pk)
    return render(request, 'students/promote.html', {'student': student})


@admin_accounts_required
def student_export_excel(request):
    from openpyxl.styles import Font, PatternFill, Alignment
    students = Student.objects.filter(is_active=True).select_related('section__group')
    group = request.GET.get('group')
    year = request.GET.get('year')
    section = request.GET.get('section')
    q = request.GET.get('q')

    if group:
        students = students.filter(section__group_id=group)
    if year:
        students = students.filter(section__year=year)
    if section:
        students = students.filter(section_id=section)
    if q:
        students = students.filter(
            Q(name__icontains=q) | Q(admission_number__icontains=q) |
            Q(hall_ticket_number__icontains=q) | Q(mobile__icontains=q) |
            Q(aadhaar__icontains=q)
        )
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Students"

    headers = [
        'Admission No', 'Hall Ticket', 'Name', 'Father Name', 'Mother Name',
        'Mobile 1', 'Mobile 2', 'Mobile 3', 'Mobile 4',
        'Aadhaar', 'Group', 'Year', 'Section', 'Address'
    ]
    col_widths = [15, 16, 28, 22, 22, 15, 15, 15, 15, 16, 18, 12, 12, 40]

    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(fill_type='solid', fgColor='1a56db')
    header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)

    for i, h in enumerate(headers, 1):
        cell = ws.cell(1, i, h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
    ws.row_dimensions[1].height = 22

    for row, s in enumerate(students, 2):
        ws.cell(row, 1, s.admission_number)
        ws.cell(row, 2, s.hall_ticket_number)
        ws.cell(row, 3, s.name)
        ws.cell(row, 4, s.father_name)
        ws.cell(row, 5, s.mother_name)
        ws.cell(row, 6, s.mobile)
        ws.cell(row, 7, s.second_mobile)
        ws.cell(row, 8, s.third_mobile)
        ws.cell(row, 9, s.fourth_mobile)
        ws.cell(row, 10, s.aadhaar)
        ws.cell(row, 11, s.section.group.name if s.section else '')
        ws.cell(row, 12, s.section.get_year_display() if s.section else '')
        ws.cell(row, 13, s.section.name if s.section else '')
        ws.cell(row, 14, s.address)
        for col in range(1, 15):
            ws.cell(row, col).alignment = Alignment(vertical='center', wrap_text=False)

    for i, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    ws.freeze_panes = 'A2'

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=students.xlsx'
    wb.save(response)
    return response


@admin_required
def student_import_excel(request):
    if request.method == 'POST' and request.FILES.get('file'):
        uploaded_file = request.FILES['file']
        if uploaded_file.size > 5 * 1024 * 1024:
            messages.error(request, 'File size exceeds limit of 5 MB.')
            return redirect('student_list')

        from accounts.models import Group
        active_year = AcademicYear.objects.filter(is_active=True).first()

        wb = None
        try:
            wb = openpyxl.load_workbook(uploaded_file, read_only=True, data_only=True)
            if len(wb.sheetnames) > 10:
                messages.error(request, 'Workbook contains too many worksheets (maximum allowed is 10).')
                return redirect('student_list')

            ws = wb.active
            row_iter = ws.iter_rows(values_only=True)
            header_row = next(row_iter, None)
            if not header_row:
                messages.error(request, 'The uploaded file is empty.')
                return redirect('student_list')

            if len(header_row) > 100:
                messages.error(request, f'Workbook exceeds maximum allowed columns limit of 100 (found {len(header_row)}).')
                return redirect('student_list')

            header = [str(h).strip().lower() if h is not None else '' for h in header_row]

            def col(*names):
                for n in names:
                    if n in header:
                        return header.index(n)
                return None

            C = {
                'adm':     col('admission no', 'admission number', 'admission_no'),
                'hall':    col('hall ticket', 'hall ticket number', 'hall_ticket'),
                'name':    col('name', 'student name'),
                'father':  col('father name', 'father'),
                'mother':  col('mother name', 'mother'),
                'mobile':  col('mobile 1', 'mobile', 'mobile1'),
                'mobile2': col('mobile 2', 'mobile2'),
                'mobile3': col('mobile 3', 'mobile3'),
                'mobile4': col('mobile 4', 'mobile4'),
                'aadhaar': col('aadhaar', 'aadhar'),
                'group':   col('group'),
                'year':    col('year'),
                'section': col('section'),
                'address': col('address'),
            }

            if C['adm'] is None or C['name'] is None:
                messages.error(request, 'File must have "Admission No" and "Name" column headers.')
                return redirect('student_list')

            def cell(row, key):
                i = C[key]
                if i is None or i >= len(row):
                    return None
                return row[i]

            def norm_year(v):
                s = str(v or '').strip().lower()
                if '2' in s:
                    return '2'
                if '1' in s:
                    return '1'
                return ''

            created = 0
            row_count = 0
            errors = []
            for row in row_iter:
                row_count += 1
                if row_count > 5000:
                    messages.error(request, 'Workbook exceeds maximum allowed rows limit of 5000.')
                    return redirect('student_list')
                try:
                    adm_no = cell(row, 'adm')
                    name = cell(row, 'name')
                    if not adm_no or not name:
                        continue

                    group_code = str(cell(row, 'group') or '').strip()
                    year_val = norm_year(cell(row, 'year'))
                    sec_name = str(cell(row, 'section') or '').strip()

                    section = None
                    if group_code and year_val and sec_name:
                        group = (Group.objects.filter(code__iexact=group_code).first()
                                 or Group.objects.filter(name__iexact=group_code).first())
                        if not group:
                            group = Group.objects.create(
                                name=group_code, code=group_code, academic_year=active_year)
                        section, _ = Section.objects.get_or_create(
                            group=group, year=year_val, name=sec_name,
                            academic_year=active_year,
                        )

                    Student.objects.update_or_create(
                        admission_number=str(adm_no),
                        defaults=dict(
                            hall_ticket_number=str(cell(row, 'hall') or ''),
                            name=str(name),
                            father_name=str(cell(row, 'father') or ''),
                            mother_name=str(cell(row, 'mother') or ''),
                            mobile=str(cell(row, 'mobile') or ''),
                            second_mobile=str(cell(row, 'mobile2') or ''),
                            third_mobile=str(cell(row, 'mobile3') or ''),
                            fourth_mobile=str(cell(row, 'mobile4') or ''),
                            aadhaar=str(cell(row, 'aadhaar') or ''),
                            address=str(cell(row, 'address') or ''),
                            section=section,
                            academic_year=active_year,
                            is_active=True,
                        )
                    )
                    created += 1
                except Exception as e:
                    errors.append(str(e))

            messages.success(request, f'{created} students imported.')
            if errors:
                messages.warning(request, f'{len(errors)} rows had errors.')
            return redirect('student_list')
        except Exception:
            messages.error(request, 'Could not parse Excel workbook.')
            return redirect('student_list')
        finally:
            if wb:
                try:
                    wb.close()
                except Exception:
                    pass
    return render(request, 'students/import.html')


@all_roles_required
def student_photo(request, pk):
    allowed_sections = _get_faculty_sections(request.user)
    student = get_object_or_404(Student.objects.filter(section__in=allowed_sections), pk=pk)
    if not student.photo:
        return HttpResponse("Photo not found", status=404)
    try:
        return HttpResponse(student.photo.read(), content_type="image/jpeg")
    except Exception:
        return HttpResponse("Photo not found", status=404)