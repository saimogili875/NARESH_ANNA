import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER


COLLEGE_NAME = "Sri NRI Junior College"


def generate_marks_report_pdf(exam, section, subjects, subject_max_marks, rows):
    """Build a marks report PDF for a section + exam.

    `rows` is a list of {'student': Student, 's_marks': {subject: Mark}, 'total': float}
    already sorted in the desired order.
    Returns raw PDF bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=16,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle", parent=styles["Normal"], alignment=TA_CENTER,
        fontSize=10, textColor=colors.grey,
    )

    elements = []
    elements.append(Paragraph(COLLEGE_NAME, title_style))
    elements.append(Paragraph(
        f"{exam.display_name()} ({exam.get_category_display()}) — {section}",
        subtitle_style
    ))
    elements.append(Spacer(1, 10))

    total_max = sum(subject_max_marks.values()) or 1
    header = ['#', 'Admission No', 'Name'] + subjects + ['Total', f'Out of {total_max}']
    data = [header]

    for idx, row in enumerate(rows, 1):
        student = row['student']
        line = [str(idx), student.admission_number, student.name]
        for sub in subjects:
            m = row['s_marks'].get(sub)
            if m:
                line.append('AB' if m.is_absent else str(m.marks_obtained))
            else:
                line.append('-')
        line.append(str(row['total']))
        line.append(f"{row['total']}/{total_max}")
        data.append(line)

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1d4ed8')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')]),
        ('FONTNAME', (0, -0), (-1, 0), 'Helvetica-Bold'),
    ]))
    elements.append(table)

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


def generate_student_marks_pdf(student, exam_rows):
    """Build a PDF of one student's marks, one row per exam with subjects
    arranged left-to-right as columns.

    `exam_rows` is a list of {'exam': Exam, 'subject_marks': [
        {'subject': str, 'mark': Mark|None, 'max': int}, ...]}
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=16,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle", parent=styles["Normal"], alignment=TA_CENTER,
        fontSize=10, textColor=colors.grey,
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4,
    )

    elements = []
    elements.append(Paragraph(COLLEGE_NAME, title_style))
    elements.append(Paragraph(
        f"Marks Report — {student.name} ({student.admission_number})",
        subtitle_style
    ))
    if student.section:
        elements.append(Paragraph(str(student.section), subtitle_style))
    elements.append(Spacer(1, 10))

    if not exam_rows:
        elements.append(Paragraph("No marks recorded yet.", styles["Normal"]))
    else:
        for entry in exam_rows:
            exam = entry['exam']
            elements.append(Paragraph(
                f"{exam.display_name()} ({exam.get_category_display()}) — {exam.date.strftime('%d %b %Y')}",
                section_style
            ))

            header = ['Subject'] + [sm['subject'] for sm in entry['subject_marks']]
            marks_row = ['Marks Obtained']
            max_row = ['Max Marks']
            total_obtained = 0
            total_max = 0
            for sm in entry['subject_marks']:
                m = sm['mark']
                if m:
                    if m.is_absent:
                        marks_row.append('AB')
                    else:
                        marks_row.append(str(m.marks_obtained))
                        total_obtained += float(m.marks_obtained or 0)
                else:
                    marks_row.append('-')
                max_row.append(str(sm['max']))
                total_max += sm['max']

            header.append('Total')
            marks_row.append(str(total_obtained))
            max_row.append(str(total_max))

            data = [header, marks_row, max_row]
            table = Table(data, repeatRows=1)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1d4ed8')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (-1, 1), (-1, -1), 'Helvetica-Bold'),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 6))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
