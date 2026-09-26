from django.shortcuts import render
from accounts.decorators import admin_accounts_required
from django.db.models import Sum, Count
from django.utils import timezone
from django.core.cache import cache
from datetime import date as date_type
from calendar import monthrange
from students.models import Student
from fees.models import StudentFee, FeePayment
from attendance.models import Attendance
from accounts.models import AcademicYear, Section


# NOTE FOR FUTURE: As historical data grows, replace live aggregation with a nightly
# management command (e.g. reports/management/commands/build_daily_summary.py) that writes
# precomputed daily attendance/fee summary rows into a small dedicated model, so reports_home()
# reads from that summary table instead of aggregating raw Attendance/FeePayment rows on every request.
@admin_accounts_required
def reports_home(request):
    today = timezone.localdate()

    # Date picker for attendance breakdown (defaults to today)
    date_str = request.GET.get('date', '')
    try:
        selected_date = date_type.fromisoformat(date_str) if date_str else today
    except ValueError:
        selected_date = today

    cache_key = f'reports_home_{selected_date.isoformat()}'
    cached = cache.get(cache_key)
    if cached is not None:
        return render(request, 'reports/home.html', cached)

    active_year = AcademicYear.objects.filter(is_active=True).first()

    total_students = Student.objects.filter(is_active=True).count()
    total_fees = StudentFee.objects.aggregate(t=Sum('total_fee'))['t'] or 0
    total_paid = FeePayment.objects.aggregate(t=Sum('amount'))['t'] or 0
    total_pending = total_fees - total_paid

    # Use explicit date range instead of __month/__year filter
    month_start = today.replace(day=1)
    last_day = monthrange(today.year, today.month)[1]
    month_end = today.replace(day=last_day)

    month_payments = FeePayment.objects.filter(
        payment_date__gte=month_start,
        payment_date__lte=month_end,
    ).aggregate(t=Sum('amount'))['t'] or 0

    # --- Section-wise attendance (single-query approach) ---
    sections = Section.objects.select_related('group').order_by('group__name', 'year', 'name')

    # Attendance counts per (section, status) for selected_date
    att_qs = (
        Attendance.objects
        .filter(date=selected_date)
        .values('section_id', 'status')
        .annotate(cnt=Count('id'))
    )
    att_by_section = {}
    for row in att_qs:
        att_by_section.setdefault(row['section_id'], {})[row['status']] = row['cnt']

    # Active student count per section
    student_count_map = {
        r['section_id']: r['cnt']
        for r in Student.objects.filter(is_active=True)
                                .values('section_id')
                                .annotate(cnt=Count('id'))
    }

    section_attendance = []
    total_present = total_absent = total_not_marked = 0

    for section in sections:
        total = student_count_map.get(section.pk, 0)
        sec_att = att_by_section.get(section.pk, {})
        present    = sec_att.get('P', 0)
        absent     = sec_att.get('A', 0)
        not_marked = max(total - present - absent, 0)
        marked     = present + absent
        pct        = round(present / marked * 100) if marked else None

        total_present    += present
        total_absent     += absent
        total_not_marked += not_marked

        section_attendance.append({
            'section': section,
            'total': total,
            'present': present,
            'absent': absent,
            'not_marked': not_marked,
            'pct': pct,
        })

    # Group-level rollup (MPIC total, BPIC total, etc.)
    group_summary = {}
    for row in section_attendance:
        g = row['section'].group.name
        entry = group_summary.setdefault(g, {'present': 0, 'absent': 0, 'total': 0})
        entry['present'] += row['present']
        entry['absent']  += row['absent']
        entry['total']   += row['total']

    context = {
        'active_year': active_year,
        'total_students': total_students,
        'total_fees': total_fees,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'month_payments': month_payments,
        'section_attendance': section_attendance,
        'group_summary': group_summary,
        'total_present': total_present,
        'total_absent': total_absent,
        'total_not_marked': total_not_marked,
        'selected_date': selected_date,
        'today': today,
    }
    cache.set(cache_key, context, 150)  # Cache for 2.5 minutes
    return render(request, 'reports/home.html', context)
