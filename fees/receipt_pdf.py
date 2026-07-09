import io
import os

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT


COLLEGE_NAME = "Sri NRI Junior College"
COLLEGE_SUBTITLE = "Fee Payment Receipt"


def generate_receipt_pdf(payment):
    """
    Build a fee payment receipt PDF for a FeePayment instance.
    Returns raw PDF bytes.
    """
    student = payment.student_fee.student
    student_fee = payment.student_fee

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A5,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReceiptTitle", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=16,
    )
    subtitle_style = ParagraphStyle(
        "ReceiptSubtitle", parent=styles["Normal"], alignment=TA_CENTER,
        fontSize=10, textColor=colors.grey,
    )
    right_style = ParagraphStyle("Right", parent=styles["Normal"], alignment=TA_RIGHT)

    elements = []
    elements.append(Paragraph(COLLEGE_NAME, title_style))
    elements.append(Paragraph(COLLEGE_SUBTITLE, subtitle_style))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f"Receipt No: <b>{payment.receipt_number}</b>", styles["Normal"]))
    elements.append(Paragraph(f"Date: {payment.payment_date.strftime('%d-%b-%Y')}", right_style))
    elements.append(Spacer(1, 10))

    student_data = [
        ["Student Name", student.name],
        ["Admission No.", student.admission_number],
        ["Section", str(student.section) if student.section else "-"],
        ["Academic Year", str(student_fee.academic_year)],
        ["Father's Name", student.father_name],
    ]
    student_table = Table(student_data, colWidths=[110, 200])
    student_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.lightgrey),
    ]))
    elements.append(student_table)
    elements.append(Spacer(1, 12))

    payment_data = [
        ["Amount Paid", f"Rs. {payment.amount:,.2f}"],
        ["Payment Mode", payment.get_payment_mode_display()],
        ["Collected By", payment.collected_by or "-"],
        ["Remarks", payment.remarks or "-"],
    ]
    payment_table = Table(payment_data, colWidths=[110, 200])
    payment_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("FONTNAME", (1, 0), (1, 0), "Helvetica-Bold"),
    ]))
    elements.append(payment_table)
    elements.append(Spacer(1, 14))

    summary_data = [
        ["Total Fee", f"Rs. {student_fee.total_fee:,.2f}"],
        ["Total Paid (incl. this)", f"Rs. {student_fee.total_paid:,.2f}"],
        ["Balance Due", f"Rs. {student_fee.total_pending:,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[150, 160])
    summary_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.grey),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"], alignment=TA_CENTER, fontSize=8, textColor=colors.grey,
    )
    elements.append(Paragraph("This is a system-generated receipt.", footer_style))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def save_receipt_pdf(payment):
    """
    Generate the receipt PDF and save it locally under MEDIA_ROOT/receipts/.
    Returns (relative_media_path, pdf_bytes), e.g. ('receipts/RCP1234.pdf', b'...').
    """
    pdf_bytes = generate_receipt_pdf(payment)

    receipts_dir = os.path.join(settings.MEDIA_ROOT, 'receipts')
    os.makedirs(receipts_dir, exist_ok=True)

    filename = f"{payment.receipt_number}.pdf"
    file_path = os.path.join(receipts_dir, filename)

    with open(file_path, 'wb') as f:
        f.write(pdf_bytes)

    relative_path = f"receipts/{filename}"
    return relative_path, pdf_bytes
