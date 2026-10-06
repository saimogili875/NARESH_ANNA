import logging
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.functions import Coalesce, TruncDate
from accounts.decorators import admin_required
from accounts.models import Group, Section
from students.models import Student
from .models import PendingMessage
from .analytics import get_analytics_data, KOLKATA_TZ

logger = logging.getLogger('whatsapp_sender')


@login_required
@admin_required
def analytics_dashboard(request):
    tab = request.GET.get('tab', 'overview').lower().strip()
    if tab not in ('overview', 'marks', 'attendance'):
        tab = 'overview'

    preset = request.GET.get('preset', 'all').lower().strip()
    from_date = request.GET.get('from_date', '').strip()
    to_date = request.GET.get('to_date', '').strip()

    # Get main analytics summary and active tab data
    analytics = get_analytics_data(preset=preset, from_str=from_date, to_str=to_date, tab=tab)

    # Filtered Message Log Queryset (25 / page)
    date_expr = Coalesce('sent_at', 'created_at')
    log_qs = PendingMessage.objects.select_related('student', 'group', 'section').annotate(
        msg_date=TruncDate(date_expr, tzinfo=KOLKATA_TZ)
    ).order_by('-created_at')

    # Apply date range from period selector to message log as well
    start_date = analytics['summary']['start_date']
    end_date = analytics['summary']['end_date']
    if start_date:
        log_qs = log_qs.filter(msg_date__gte=start_date)
    if end_date:
        log_qs = log_qs.filter(msg_date__lte=end_date)

    # Additional filter params
    q_search = request.GET.get('q', '').strip()
    filter_student_id = request.GET.get('student', '').strip()
    filter_admission = request.GET.get('admission_no', '').strip()
    filter_group_id = request.GET.get('group', '').strip()
    filter_section_id = request.GET.get('section', '').strip()
    filter_type = request.GET.get('type', '').strip().upper()
    filter_status = request.GET.get('status', '').strip().lower()

    if q_search:
        log_qs = log_qs.filter(
            Q(student__name__icontains=q_search) |
            Q(student__admission_number__icontains=q_search) |
            Q(phone__icontains=q_search) |
            Q(wamid__icontains=q_search) |
            Q(template_name__icontains=q_search)
        )
    if filter_student_id and filter_student_id.isdigit():
        log_qs = log_qs.filter(student_id=int(filter_student_id))
    if filter_admission:
        log_qs = log_qs.filter(student__admission_number__icontains=filter_admission)
    if filter_group_id and filter_group_id.isdigit():
        log_qs = log_qs.filter(group_id=int(filter_group_id))
    if filter_section_id and filter_section_id.isdigit():
        log_qs = log_qs.filter(section_id=int(filter_section_id))
    if filter_type in (PendingMessage.CATEGORY_MARKS, PendingMessage.CATEGORY_ATTENDANCE, PendingMessage.CATEGORY_OTHER):
        log_qs = log_qs.filter(category=filter_type)
    if filter_status in dict(PendingMessage.STATUS_CHOICES):
        log_qs = log_qs.filter(status=filter_status)

    paginator = Paginator(log_qs, 25)
    page_number = request.GET.get('page', 1)
    log_page = paginator.get_page(page_number)

    groups = Group.objects.all()
    sections = Section.objects.select_related('group').all()

    context = {
        'active_tab': tab,
        'summary': analytics['summary'],
        'tab_data': analytics['tab_data'],
        'log_page': log_page,
        'groups': groups,
        'sections': sections,
        'q_search': q_search,
        'filter_student_id': filter_student_id,
        'filter_admission': filter_admission,
        'filter_group_id': filter_group_id,
        'filter_section_id': filter_section_id,
        'filter_type': filter_type,
        'filter_status': filter_status,
        'preset': preset,
        'from_date': from_date,
        'to_date': to_date,
    }

    return render(request, 'whatsapp/analytics.html', context)
