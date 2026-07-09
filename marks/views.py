from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse
from .models import Exam, Mark, ExamSubjectMaxMark, ExamCategory, ExamType, GroupCategoryConfig, Subject
from students.models import Student
from accounts.models import Section, AcademicYear, Group
from accounts.decorators import all_roles_required, admin_faculty_required

def get_subjects_for_exam(exam):
    """Return the subject list to use for marks entry/report for this exam."""
    if exam.category_id:
        return list(exam.category.subjects.all())
    return list(Subject.objects.all())

def get_subject_max_marks(exam, subjects):
    """Return {subject: max_marks} for the given exam."""
    saved = {m.subject: m.max_marks for m in exam.subject_max_marks.select_related('subject')}
    return {sub: saved.get(sub, exam.max_marks) for sub in subjects}

@all_roles_required
def exam_list(request):
    active_year = AcademicYear.objects.filter(is_active=True).first()
    all_exams = (
        Exam.objects.filter(academic_year=active_year).select_related('group', 'category', 'exam_type').order_by('-date')
        if active_year else []
    )
    categories_qs = ExamCategory.objects.all()
    exam_boxes = []
    for cat in categories_qs:
        cat_exams = [e for e in all_exams if e.category_id == cat.id]
        exam_boxes.append({
            'key': str(cat.id), 'label': cat.name,
            'bg': cat.bg_color, 'color': cat.text_color, 'icon': cat.icon,
            'exams': cat_exams,
        })
    return render(request, 'marks/exam_list.html', {
        'exams': all_exams,
        'exam_boxes': exam_boxes,
        'active_year': active_year,
    })

@admin_faculty_required
def exam_add(request):
    active_year = AcademicYear.objects.filter(is_active=True).first()
    groups = Group.objects.all().order_by('name')
    exam_types = ExamType.objects.all()
    categories_qs = ExamCategory.objects.all()
    
    cl_data = {str(c.id): c.name for c in categories_qs}
    fc_data = [str(c.id) for c in categories_qs if c.is_fixed_marks]
    
    gco_data = {}
    ss_data = {}
    for config in GroupCategoryConfig.objects.select_related('group', 'category'):
        g_pk = str(config.group.pk)
        c_pk = str(config.category.pk)
        gco_data.setdefault(g_pk, []).append(c_pk)

    for cat in categories_qs.prefetch_related('subjects'):
        ss_data[str(cat.id)] = [sub.name for sub in cat.subjects.all()]
        
    exam_types_js = [[str(et.id), et.name] for et in exam_types]

    if request.method == 'POST':
        exam_type_id = request.POST.get('exam_type')
        custom_name = request.POST.get('custom_name', '').strip()
        group_id = request.POST.get('group_id')
        category_id = request.POST.get('category')

        if not group_id:
            messages.error(request, 'Please select a Student Group.')
        else:
            group = get_object_or_404(Group, pk=group_id)
            category = get_object_or_404(ExamCategory, pk=category_id)
            exam_type = get_object_or_404(ExamType, pk=exam_type_id)

            subjects = list(category.subjects.all())

            subject_max_inputs = {}
            if category.is_fixed_marks:
                overall_max = 100 * len(subjects) # simple default for now, can be adjusted
            else:
                for subject in subjects:
                    val = request.POST.get(f'subject_max_{subject.name}', '').strip()
                    try:
                        subject_max_inputs[subject] = int(val) if val else 100
                    except (TypeError, ValueError):
                        subject_max_inputs[subject] = 100
                overall_max = sum(subject_max_inputs.values()) or 100

            exam = Exam.objects.create(
                exam_type=exam_type,
                custom_name=custom_name if exam_type.name.lower() == 'custom' else '',
                academic_year=active_year,
                group=group,
                category=category,
                date=request.POST.get('date'),
                max_marks=overall_max,
            )

            if not category.is_fixed_marks:
                for subject, sub_max in subject_max_inputs.items():
                    ExamSubjectMaxMark.objects.update_or_create(
                        exam=exam, subject=subject, defaults={'max_marks': sub_max}
                    )

            messages.success(request, 'Exam created successfully.')
            return redirect('exam_list')

    return render(request, 'marks/exam_form.html', {
        'active_year': active_year, 'exam_types': exam_types,
        'groups': groups,
        'group_category_options': gco_data,
        'category_labels': cl_data,
        'subject_sets': ss_data,
        'fixed_categories': fc_data,
        'exam_types_js': exam_types_js,
        'default_max_marks': {str(c.id): 100 for c in categories_qs},
        'fixed_subject_max_marks': {str(c.id): {} for c in categories_qs if c.is_fixed_marks},
    })

@admin_faculty_required
def marks_entry(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    section_id = request.GET.get('section', '')
    if exam.group_id:
        sections = Section.objects.select_related('group').filter(group=exam.group)
    else:
        sections = Section.objects.select_related('group').all()
    subjects = get_subjects_for_exam(exam)
    subject_max_marks = get_subject_max_marks(exam, subjects)
    rows = []
    selected_section = None

    if request.method == 'POST':
        sid = request.POST.get('section_id')
        sec = get_object_or_404(Section, pk=sid)
        for student in Student.objects.filter(section=sec, is_active=True):
            for subject in subjects:
                val = request.POST.get(f'mark_{student.pk}_{subject.name}', '').strip()
                if val:
                    Mark.objects.update_or_create(
                        student=student, exam=exam, subject=subject,
                        defaults={'marks_obtained': val, 'is_absent': False}
                    )
        messages.success(request, 'Marks saved successfully.')
        return redirect(f'/marks/exam/{exam_id}/entry/?section={sid}')

    if section_id and str(section_id).isdigit():
        selected_section = get_object_or_404(Section, pk=section_id)
        students = list(Student.objects.filter(section=selected_section, is_active=True))
        existing = Mark.objects.filter(exam=exam, student__in=students)
        marks_map = {}
        for m in existing:
            marks_map.setdefault(m.student_id, {})[m.subject_id] = m.marks_obtained or ''
        for student in students:
            s_marks = [(sub, marks_map.get(student.pk, {}).get(sub.id, '')) for sub in subjects]
            rows.append({'student': student, 'marks': s_marks})

    subjects_with_max = [(sub, subject_max_marks.get(sub, exam.max_marks)) for sub in subjects]

    return render(request, 'marks/entry.html', {
        'exam': exam, 'sections': sections, 'rows': rows,
        'selected_section': selected_section, 'section_id': str(section_id),
        'subjects': subjects, 'subject_max_marks': subject_max_marks,
        'subjects_with_max': subjects_with_max,
    })

@all_roles_required
def marks_report(request):
    import json
    group_id   = request.GET.get('group', '')
    category   = request.GET.get('category', '')
    section_id = request.GET.get('section', '')
    exam_id    = request.GET.get('exam', '')
    sort_order = request.GET.get('sort', 'asc')

    groups   = Group.objects.all().order_by('name')
    sections = Section.objects.select_related('group').all()
    active_year = AcademicYear.objects.filter(is_active=True).first()
    exams = Exam.objects.filter(academic_year=active_year).select_related('group', 'category', 'exam_type').order_by('-date') if active_year else []
    categories_qs = ExamCategory.objects.all()

    group_category_map = {}
    for config in GroupCategoryConfig.objects.select_related('group', 'category').all():
        group_category_map.setdefault(str(config.group_id), []).append(str(config.category_id))
    group_category_map_json = json.dumps(group_category_map)

    report_data = []
    selected_section = None
    selected_exam = None
    section_label = ''
    subjects = []
    subject_max_marks = {}
    total_max = 0
    is_all_exams = False
    all_exams_list = []

    eff_group    = None if (not group_id    or group_id    == 'all') else group_id
    eff_category = None if (not category    or category    == 'all') else category
    eff_section  = None if (not section_id  or section_id  == 'all') else section_id

    def _resolve_students():
        nonlocal selected_section, section_label
        if eff_section:
            selected_section = get_object_or_404(Section, pk=eff_section)
            section_label = str(selected_section)
            return Student.objects.filter(section=selected_section, is_active=True)
        qs = Student.objects.select_related('section').filter(is_active=True)
        if eff_group:
            qs = qs.filter(section__group_id=eff_group)
        section_label = 'All Sections'
        return qs

    if section_id and exam_id:
        if exam_id == 'all':
            is_all_exams = True
            students = _resolve_students()

            exam_qs = Exam.objects.filter(academic_year=active_year).select_related('group').order_by('date')
            if eff_group:
                exam_qs = exam_qs.filter(group_id=eff_group)
            if eff_category:
                exam_qs = exam_qs.filter(category_id=eff_category)
            all_exams_list = list(exam_qs)

            all_marks = Mark.objects.filter(exam__in=all_exams_list, student__in=students)
            exam_total_map = {}
            for m in all_marks:
                if m.marks_obtained and not m.is_absent:
                    exam_total_map.setdefault(m.student_id, {})
                    exam_total_map[m.student_id][m.exam_id] = (
                        exam_total_map[m.student_id].get(m.exam_id, 0) + float(m.marks_obtained)
                    )
            for student in students:
                s_totals = exam_total_map.get(student.pk, {})
                per_exam = [round(s_totals.get(e.pk, 0), 1) for e in all_exams_list]
                overall = round(sum(per_exam), 1)
                report_data.append({'student': student, 'per_exam': per_exam, 'total': overall})

            reverse = (sort_order == 'desc')
            report_data.sort(key=lambda r: r['total'], reverse=reverse)

        else:
            selected_exam = get_object_or_404(Exam, pk=exam_id)
            students = _resolve_students()

            marks = Mark.objects.filter(exam=selected_exam, student__in=students).select_related('subject')
            subjects_dict = {}
            for m in marks:
                if m.subject_id not in subjects_dict:
                    subjects_dict[m.subject_id] = m.subject
            subjects = sorted(list(subjects_dict.values()), key=lambda x: x.name)
            if not subjects:
                subjects = get_subjects_for_exam(selected_exam)
            subject_max_marks = get_subject_max_marks(selected_exam, subjects)
            total_max = sum(subject_max_marks.get(sub, 0) for sub in subjects)
            marks_map = {}
            for m in marks:
                marks_map.setdefault(m.student_id, {})[m.subject_id] = m
            for student in students:
                s_marks = marks_map.get(student.pk, {})
                mark_list = [s_marks.get(sub.id) for sub in subjects]
                total = sum(float(m.marks_obtained) for m in s_marks.values()
                           if m.marks_obtained and not m.is_absent)
                pct = round(total / total_max * 100, 1) if total_max else 0
                report_data.append({'student': student, 'mark_list': mark_list, 'total': total, 'pct': pct})

            reverse = (sort_order == 'desc')
            report_data.sort(key=lambda r: r['total'], reverse=reverse)

    subjects_with_max = [(sub, subject_max_marks.get(sub, 0)) for sub in subjects]

    return render(request, 'marks/report.html', {
        'groups': groups,
        'category_choices': [(c.id, c.name) for c in categories_qs],
        'group_category_map_json': group_category_map_json,
        'sections': sections, 'exams': exams, 'report_data': report_data,
        'selected_section': selected_section, 'selected_exam': selected_exam,
        'section_label': section_label,
        'is_all_exams': is_all_exams, 'all_exams_list': all_exams_list,
        'group_id': str(group_id), 'category': category,
        'section_id': str(section_id), 'exam_id': str(exam_id), 'subjects': subjects,
        'subject_max_marks': subject_max_marks, 'total_max': total_max,
        'sort_order': sort_order, 'subjects_with_max': subjects_with_max,
    })

@all_roles_required
def marks_report_export_excel(request):
    import openpyxl

    section_id = request.GET.get('section', '')
    exam_id = request.GET.get('exam', '')
    sort_order = request.GET.get('sort', 'asc')

    if not (section_id and exam_id):
        messages.error(request, 'Please select a section and exam before exporting.')
        return redirect('marks_report')

    selected_section = get_object_or_404(Section, pk=section_id)
    selected_exam = get_object_or_404(Exam, pk=exam_id)
    students = Student.objects.filter(section=selected_section, is_active=True)
    marks = Mark.objects.filter(exam=selected_exam, student__in=students).select_related('subject')
    subjects_dict = {}
    for m in marks:
        if m.subject_id not in subjects_dict:
            subjects_dict[m.subject_id] = m.subject
    subjects = sorted(list(subjects_dict.values()), key=lambda x: x.name)
    if not subjects:
        subjects = get_subjects_for_exam(selected_exam)
    subject_max_marks = get_subject_max_marks(selected_exam, subjects)

    marks_map = {}
    for m in marks:
        marks_map.setdefault(m.student_id, {})[m.subject_id] = m

    rows = []
    for student in students:
        s_marks = marks_map.get(student.pk, {})
        total = sum(float(m.marks_obtained) for m in s_marks.values()
                   if m.marks_obtained and not m.is_absent)
        rows.append({'student': student, 's_marks': s_marks, 'total': total})

    reverse = (sort_order == 'desc')
    rows.sort(key=lambda r: r['total'], reverse=reverse)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Marks Report"

    headers = ['#', 'Admission No', 'Name'] + [s.name for s in subjects] + ['Total', f'Total (out of {sum(subject_max_marks.values())})']
    for i, h in enumerate(headers, 1):
        ws.cell(1, i, h)

    for idx, row in enumerate(rows, 1):
        ws.cell(idx + 1, 1, idx)
        ws.cell(idx + 1, 2, row['student'].admission_number)
        ws.cell(idx + 1, 3, row['student'].name)
        for j, sub in enumerate(subjects):
            m = row['s_marks'].get(sub.id)
            if m:
                ws.cell(idx + 1, 4 + j, 'AB' if m.is_absent else float(m.marks_obtained or 0))
            else:
                ws.cell(idx + 1, 4 + j, '-')
        col_total = 4 + len(subjects)
        ws.cell(idx + 1, col_total, row['total'])
        ws.cell(idx + 1, col_total + 1, f"{row['total']}/{sum(subject_max_marks.values())}")

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    filename = f"marks_report_{selected_exam.display_name()}_{selected_section}.xlsx".replace(' ', '_')
    response['Content-Disposition'] = f'attachment; filename={filename}'
    wb.save(response)
    return response

@all_roles_required
def marks_report_export_pdf(request):
    from .marks_pdf import generate_marks_report_pdf

    section_id = request.GET.get('section', '')
    exam_id = request.GET.get('exam', '')
    sort_order = request.GET.get('sort', 'asc')

    if not (section_id and exam_id):
        messages.error(request, 'Please select a section and exam before exporting.')
        return redirect('marks_report')

    selected_section = get_object_or_404(Section, pk=section_id)
    selected_exam = get_object_or_404(Exam, pk=exam_id)
    students = Student.objects.filter(section=selected_section, is_active=True)
    marks = Mark.objects.filter(exam=selected_exam, student__in=students).select_related('subject')
    subjects_dict = {}
    for m in marks:
        if m.subject_id not in subjects_dict:
            subjects_dict[m.subject_id] = m.subject
    subjects = sorted(list(subjects_dict.values()), key=lambda x: x.name)
    if not subjects:
        subjects = get_subjects_for_exam(selected_exam)
    subject_max_marks = get_subject_max_marks(selected_exam, subjects)

    marks_map = {}
    for m in marks:
        marks_map.setdefault(m.student_id, {})[m.subject_id] = m

    rows = []
    for student in students:
        s_marks = marks_map.get(student.pk, {})
        total = sum(float(m.marks_obtained) for m in s_marks.values()
                   if m.marks_obtained and not m.is_absent)
        rows.append({'student': student, 's_marks': s_marks, 'total': total})

    reverse = (sort_order == 'desc')
    rows.sort(key=lambda r: r['total'], reverse=reverse)

    pdf_bytes = generate_marks_report_pdf(selected_exam, selected_section, subjects, subject_max_marks, rows)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f"marks_report_{selected_exam.display_name()}_{selected_section}.pdf".replace(' ', '_')
    response['Content-Disposition'] = f'attachment; filename={filename}'
    return response

@all_roles_required
def student_marks_export_pdf(request, student_id):
    from .marks_pdf import generate_student_marks_pdf

    student = get_object_or_404(Student, pk=student_id)
    marks = Mark.objects.filter(student=student).select_related('exam', 'subject').order_by('-exam__date')

    exams_map = {}
    for m in marks:
        exams_map.setdefault(m.exam_id, {'exam': m.exam, 'marks': {}})
        exams_map[m.exam_id]['marks'][m.subject_id] = m

    exam_rows = []
    for entry in exams_map.values():
        exam = entry['exam']
        subjects = get_subjects_for_exam(exam)
        subject_max_marks = get_subject_max_marks(exam, subjects)
        row_marks = []
        for sub in subjects:
            m = entry['marks'].get(sub.id)
            row_marks.append({
                'subject': sub.name,
                'mark': m,
                'max': subject_max_marks.get(sub, exam.max_marks),
            })
        exam_rows.append({'exam': exam, 'subject_marks': row_marks})

    pdf_bytes = generate_student_marks_pdf(student, exam_rows)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f"marks_{student.admission_number}_{student.name}.pdf".replace(' ', '_')
    response['Content-Disposition'] = f'attachment; filename={filename}'
    return response

@all_roles_required
def marks_report_export(request):
    fmt = request.GET.get('export', 'pdf')
    section_id = request.GET.get('section', '')
    exam_id    = request.GET.get('exam', '')
    if not (section_id and exam_id):
        messages.error(request, 'Please select section and exam first.')
        return redirect('marks_report')
    from django.urls import reverse
    base = reverse('marks_report_export_excel') if fmt == 'excel' else reverse('marks_report_export_pdf')
    return redirect(f"{base}?section={section_id}&exam={exam_id}")
