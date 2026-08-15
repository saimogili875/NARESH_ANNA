import io
import os

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT


COLLEGE_NAME = "Sri NRI Junior College"
COLLEGE_SUBTITLE = "Fee Payment Receipt"
COLLEGE_ADDRESS = "Behind Bharath Petrol Pump, Hyderabad - Nagarjuna Sagar Rd, B N Reddy Nagar, Hyderabad-500070, Telangana"
LOGO_PATH = os.path.join(settings.BASE_DIR, "static", "images", "sri_nri_logo.png")


def get_logo_path():
    primary = os.path.join(settings.BASE_DIR, "static", "images", "sri_nri_logo.png")
    if os.path.exists(primary):
        return primary
    fallback = os.path.join(settings.BASE_DIR, "static", "srinri_logo.png")
    if os.path.exists(fallback):
        return fallback
    return None


def draw_watermark(canvas, doc):
    """Draw a faint logo watermark centered on the top 1/3 receipt block of the A4 page canvas."""
    canvas.saveState()
    width, height = doc.pagesize
    logo_file = get_logo_path()
    if logo_file:
        try:
            if hasattr(canvas, 'setFillAlpha'):
                canvas.setFillAlpha(0.08)
                canvas.setStrokeAlpha(0.08)
            img_w, img_h = 60 * mm, 60 * mm
            x = (width - img_w) / 2
            y_top = (height * 5 / 6) - (img_h / 2)
            canvas.drawImage(logo_file, x, y_top, width=img_w, height=img_h, mask='auto', preserveAspectRatio=True)
        except Exception:
            pass
    canvas.restoreState()


def generate_receipt_pdf(payment):
    """
    Build a single fee payment receipt PDF formatted on top 1/3 of an A4 page.
    Features modern horizontal layout (Student Information first), ending with a scissor cut line.
    Returns raw PDF bytes.
    """
    student = payment.student_fee.student
    student_fee = payment.student_fee

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=5 * mm,
        bottomMargin=5 * mm,
        leftMargin=8 * mm,
        rightMargin=8 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReceiptTitle", parent=styles["Heading1"],
        fontSize=13, leading=15, textColor=colors.HexColor("#b91c1c"), fontName="Helvetica-Bold"
    )
    address_style = ParagraphStyle(
        "ReceiptAddress", parent=styles["Normal"],
        fontSize=6.5, leading=8.5, textColor=colors.HexColor("#4b5563")
    )
    subtitle_style = ParagraphStyle(
        "ReceiptSubtitle", parent=styles["Normal"],
        fontSize=9, leading=11, textColor=colors.HexColor("#1e40af"), fontName="Helvetica-Bold"
    )

    sec_heading_style = ParagraphStyle(
        "SecHead", parent=styles["Normal"],
        fontSize=8.5, leading=10.5, textColor=colors.HexColor("#1e40af"), fontName="Helvetica-Bold"
    )
    label_style = ParagraphStyle(
        "Lbl", parent=styles["Normal"],
        fontSize=8, leading=10, textColor=colors.HexColor("#6b7280"), fontName="Helvetica-Bold"
    )
    val_style = ParagraphStyle(
        "Val", parent=styles["Normal"],
        fontSize=8, leading=10, textColor=colors.HexColor("#111827")
    )
    val_bold_style = ParagraphStyle(
        "ValBold", parent=styles["Normal"],
        fontSize=8.5, leading=10.5, textColor=colors.HexColor("#111827"), fontName="Helvetica-Bold"
    )
    val_amt_style = ParagraphStyle(
        "ValAmt", parent=styles["Normal"],
        fontSize=10, leading=12, textColor=colors.HexColor("#15803d"), fontName="Helvetica-Bold"
    )

    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"], alignment=TA_CENTER,
        fontSize=7.5, textColor=colors.HexColor("#9ca3af")
    )
    cut_line_style = ParagraphStyle(
        "CutLine", parent=styles["Normal"], alignment=TA_CENTER,
        fontSize=7.5, textColor=colors.HexColor("#9ca3af")
    )

    logo_file = get_logo_path()

    elements = []

    # Header Block
    text_flowables = [
        Paragraph(f"<b>{COLLEGE_NAME}</b>", title_style),
        Spacer(1, 1),
        Paragraph(COLLEGE_ADDRESS, address_style),
        Spacer(1, 2),
        Paragraph(f"<b>{COLLEGE_SUBTITLE}</b>", subtitle_style),
    ]

    if logo_file:
        img = Image(logo_file, width=18 * mm, height=18 * mm, kind='proportional')
        hdr_table = Table([[img, text_flowables]], colWidths=[20 * mm, 174 * mm])
        hdr_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(hdr_table)
    else:
        elements.extend(text_flowables)

    elements.append(Spacer(1, 3))

    # Thin Header Accent Line
    line_table = Table([['']], colWidths=[194 * mm], rowHeights=[1.2])
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#1e40af')),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(line_table)
    elements.append(Spacer(1, 4))

    def sec_heading(title, w=94 * mm):
        t = Table([[Paragraph(f"<b>{title}</b>", sec_heading_style)]], colWidths=[w])
        t.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (-1, -1), 0.75, colors.HexColor('#bfdbfe')),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
        ]))
        return t

    def key_val_table(pairs, w=94 * mm):
        rows = []
        for l, v in pairs:
            is_amt = 'Rs.' in str(v)
            v_st = val_amt_style if is_amt else (val_bold_style if '<b>' in str(v) else val_style)
            rows.append([Paragraph(l, label_style), Paragraph(str(v), v_st)])
        t = Table(rows, colWidths=[30 * mm, w - 30 * mm])
        t.setStyle(TableStyle([
            ('TOPPADDING', (0, 0), (-1, -1), 1.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        return t

    # Left Column: Student Information (First!) + Receipt & Academic Details
    left_flowables = [
        sec_heading("Student Information", 94 * mm),
        Spacer(1, 1),
        key_val_table([
            ("Student Name", f"<b>{student.name}</b>"),
            ("Father's Name", student.father_name),
            ("Admission No.", student.admission_number),
            ("Section", str(student.section) if student.section else "-"),
        ], 94 * mm),
        Spacer(1, 3),
        sec_heading("Receipt & Academic Details", 94 * mm),
        Spacer(1, 1),
        key_val_table([
            ("Receipt No.", f"<b>{payment.receipt_number}</b>"),
            ("Receipt Date", payment.payment_date.strftime('%d-%b-%Y')),
            ("Academic Year", str(student_fee.academic_year)),
        ], 94 * mm),
    ]

    # Right Column: Payment Information + Additional Details
    right_flowables = [
        sec_heading("Payment Information", 94 * mm),
        Spacer(1, 1),
        key_val_table([
            ("Amount Paid", f"<b>Rs. {payment.amount:,.2f}</b>"),
            ("Payment Mode", payment.get_payment_mode_display()),
        ], 94 * mm),
        Spacer(1, 3),
        sec_heading("Additional Details", 94 * mm),
        Spacer(1, 1),
        key_val_table([
            ("Collected By", payment.collected_by or "-"),
            ("Remarks", payment.remarks or "-"),
        ], 94 * mm),
    ]

    grid = Table([[left_flowables, right_flowables]], colWidths=[94 * mm, 94 * mm])
    grid.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 3 * mm),
        ('LEFTPADDING', (1, 0), (1, 0), 3 * mm),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(grid)
    elements.append(Spacer(1, 4))
    elements.append(Paragraph("This is a system-generated receipt.", footer_style))
    elements.append(Spacer(1, 6))

    # Scissor Cut Line separating 1/3 receipt from bottom 2/3 paper
    cut_table = Table([[Paragraph("✂ - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - Cut Here - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -", cut_line_style)]], colWidths=[194 * mm])
    cut_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(cut_table)

    doc.build(elements, onFirstPage=draw_watermark, onLaterPages=draw_watermark)
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
