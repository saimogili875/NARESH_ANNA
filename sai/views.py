from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from students.models import Student
from .forms import LabPerformanceReportForm
from .models import LabPerformanceReport
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from datetime import datetime
import io





@require_http_methods(["GET", "POST"])
def lab_form(request):
    """Display lab performance form and handle submission."""
    if request.method == 'POST':
        
        form = LabPerformanceReportForm(request.POST)
        if form.is_valid():
            report = form.save()
            messages.success(request, f'Report for {report.student.name} saved successfully!')
            return redirect('sai:lab_form_success', report_id=report.id)
    else:
        form = LabPerformanceReportForm()
    
    return render(request, 'sai/lab_form.html', {'form': form})


@require_http_methods(["GET"])
def lab_form_success(request, report_id):
    """Show success page with options to print or preview the PDF."""
    report = get_object_or_404(LabPerformanceReport, id=report_id)
    return render(request, 'sai/lab_form_success.html', {'report': report})


@require_http_methods(["GET"])
def lab_preview(request, report_id):
    """Show a JavaScript-powered live preview page for the PDF."""
    report = get_object_or_404(LabPerformanceReport, id=report_id)
    return render(request, 'sai/lab_preview.html', {'report': report})


@require_http_methods(["GET"])
def generate_pdf(request, report_id):
    """Generate and download PDF report."""
    report = get_object_or_404(LabPerformanceReport, id=report_id)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Lab_Report_{report.student.name}_{report.student.admission_number}.pdf"'

    pdf = canvas.Canvas(response, pagesize=A4)

    pdf.setFont('Helvetica-Bold', 18)
    pdf.drawString(100, 770, 'SRI CHAITANYA JUNIOR COLLEGE')
    pdf.setFont('Helvetica', 12)
    pdf.drawString(100, 750, 'Student Performance Report')

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(100, 710, 'Student Name:')
    pdf.setFont('Helvetica', 12)
    pdf.drawString(220, 710, report.student.name)

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(100, 690, 'Admission No:')
    pdf.setFont('Helvetica', 12)
    pdf.drawString(220, 690, report.student.admission_number)

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(100, 670, 'Hall Ticket No:')
    pdf.setFont('Helvetica', 12)
    pdf.drawString(220, 670, report.student.hall_ticket_number or 'N/A')

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(100, 650, 'Course:')
    pdf.setFont('Helvetica', 12)
    pdf.drawString(220, 650, report.student.group.name if report.student.group else 'N/A')

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(100, 630, 'Section:')
    pdf.setFont('Helvetica', 12)
    pdf.drawString(220, 630, report.student.section.name if report.student.section else 'N/A')

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(100, 600, 'JEE Main Best:')
    pdf.setFont('Helvetica', 12)
    pdf.drawString(220, 600, str(report.jee_best_score or 'N/A'))

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(100, 580, 'JEE Main Avg:')
    pdf.setFont('Helvetica', 12)
    pdf.drawString(220, 580, str(report.jee_avg_score or 'N/A'))

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(100, 560, 'EAMCET Best:')
    pdf.setFont('Helvetica', 12)
    pdf.drawString(220, 560, str(report.eamcet_best_score or 'N/A'))

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(100, 540, 'EAMCET Avg:')
    pdf.setFont('Helvetica', 12)
    pdf.drawString(220, 540, str(report.eamcet_avg_score or 'N/A'))

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(100, 520, 'IPE Score:')
    pdf.setFont('Helvetica', 12)
    pdf.drawString(220, 520, str(report.ipe_score or 'N/A'))

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(100, 500, 'IPE %:')
    pdf.setFont('Helvetica', 12)
    pdf.drawString(220, 500, str(report.ipe_percentage or 'N/A'))

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(100, 480, 'Weekly Avg:')
    pdf.setFont('Helvetica', 12)
    pdf.drawString(220, 480, str(report.weekly_avg_score or 'N/A'))

    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(100, 450, 'Remarks:')
    pdf.setFont('Helvetica', 12)
    pdf.drawString(100, 430, report.remarks or 'N/A')


    pdf.showPage()
    pdf.save()

    return response


@require_http_methods(["GET"])
def lab_reports_list(request):
    """Show list of all lab reports."""
    reports = LabPerformanceReport.objects.select_related('student', 'academic_year').all()
    
    # Filter by student if provided
    student_id = request.GET.get('student')
    if student_id:
        reports = reports.filter(student_id=student_id)
    
    students = Student.objects.filter(is_active=True).order_by('name')
    
    return render(request, 'sai/lab_reports_list.html', {
        'reports': reports,
        'students': students,
        'selected_student': student_id,
    })


@require_http_methods(["GET"])
def lab_report_detail(request, report_id):
    """Show detailed report view."""
    report = get_object_or_404(LabPerformanceReport, id=report_id)
    return render(request, 'sai/lab_report_detail.html', {'report': report})
