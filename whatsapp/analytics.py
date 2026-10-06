import logging
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from django.utils import timezone
from django.db.models import Count, Q, F
from django.db.models.functions import Coalesce, TruncDate
from students.models import Student
from .models import PendingMessage

logger = logging.getLogger('whatsapp_sender')
KOLKATA_TZ = ZoneInfo('Asia/Kolkata')


def get_date_range(preset='all', from_str=None, to_str=None):
    now_local = timezone.now().astimezone(KOLKATA_TZ)
    today = now_local.date()

    if preset == 'today':
        return today, today
    elif preset == 'yesterday':
        y = today - timedelta(days=1)
        return y, y
    elif preset == '7d':
        return today - timedelta(days=6), today
    elif preset == '30d':
        return today - timedelta(days=29), today
    elif preset == 'custom' and from_str and to_str:
        try:
            d1 = datetime.strptime(str(from_str).strip(), '%Y-%m-%d').date()
            d2 = datetime.strptime(str(to_str).strip(), '%Y-%m-%d').date()
            if d1 > d2:
                d1, d2 = d2, d1
            return d1, d2
        except Exception:
            return None, None
    return None, None


def get_section_label(sec, grp):
    if sec:
        return str(sec)
    if grp:
        return f"{grp.code} (Unassigned Section)"
    return "Unassigned"


def get_analytics_data(preset='all', from_str=None, to_str=None, tab='overview'):
    start_date, end_date = get_date_range(preset, from_str, to_str)

    # Base queryset for student messages of category MARKS or ATTENDANCE
    qs = PendingMessage.objects.filter(
        student__isnull=False,
        category__in=[PendingMessage.CATEGORY_MARKS, PendingMessage.CATEGORY_ATTENDANCE]
    ).select_related('student', 'group', 'section')

    # Truncate Coalesce(sent_at, created_at) to Asia/Kolkata date
    date_expr = Coalesce('sent_at', 'created_at')
    qs = qs.annotate(msg_date=TruncDate(date_expr, tzinfo=KOLKATA_TZ))

    if start_date:
        qs = qs.filter(msg_date__gte=start_date)
    if end_date:
        qs = qs.filter(msg_date__lte=end_date)

    # Sent messages exclude pending/processing. Failed messages are a SUBSET of Sent.
    sent_qs = qs.exclude(status__in=[PendingMessage.STATUS_PENDING, PendingMessage.STATUS_PROCESSING])

    total_sent = sent_qs.count()
    total_delivered = sent_qs.filter(status__in=[PendingMessage.STATUS_DELIVERED, PendingMessage.STATUS_READ]).count()
    total_read = sent_qs.filter(status=PendingMessage.STATUS_READ).count()
    total_failed = sent_qs.filter(status=PendingMessage.STATUS_FAILED).count()
    total_queued = qs.filter(status__in=[PendingMessage.STATUS_PENDING, PendingMessage.STATUS_PROCESSING]).count()

    total_marks = sent_qs.filter(category=PendingMessage.CATEGORY_MARKS).count()
    total_attendance = sent_qs.filter(category=PendingMessage.CATEGORY_ATTENDANCE).count()

    unique_students = sent_qs.values('student_id').distinct().count()
    msgs_per_student = round(total_sent / unique_students, 2) if unique_students > 0 else 0.0
    total_active_students = Student.objects.filter(is_active=True).count()

    # Meta explainer count: excluded messages (faculty or category OTHER)
    other_or_faculty_count = PendingMessage.objects.filter(
        Q(student__isnull=True) | Q(category=PendingMessage.CATEGORY_OTHER)
    ).count()

    summary = {
        'total_active_students': total_active_students,
        'total_sent': total_sent,
        'total_delivered': total_delivered,
        'total_read': total_read,
        'total_failed': total_failed,
        'total_queued': total_queued,
        'total_marks': total_marks,
        'total_attendance': total_attendance,
        'unique_students': unique_students,
        'msgs_per_student': msgs_per_student,
        'other_or_faculty_count': other_or_faculty_count,
        'preset': preset,
        'start_date': start_date.strftime('%Y-%m-%d') if start_date else '',
        'end_date': end_date.strftime('%Y-%m-%d') if end_date else '',
    }

    tab_data = {}

    if tab == 'overview':
        # 1. Date Stacked Bar Data
        date_rows = (
            sent_qs.values('msg_date')
            .annotate(
                marks_count=Count('id', filter=Q(category=PendingMessage.CATEGORY_MARKS)),
                att_count=Count('id', filter=Q(category=PendingMessage.CATEGORY_ATTENDANCE)),
                total_sent=Count('id'),
                delivered_count=Count('id', filter=Q(status__in=[PendingMessage.STATUS_DELIVERED, PendingMessage.STATUS_READ])),
                read_count=Count('id', filter=Q(status=PendingMessage.STATUS_READ)),
                failed_count=Count('id', filter=Q(status=PendingMessage.STATUS_FAILED)),
                unique_students=Count('student_id', distinct=True)
            )
            .order_by('msg_date')
        )

        date_labels = []
        date_marks = []
        date_attendance = []
        date_table = []

        for row in date_rows:
            d_str = row['msg_date'].strftime('%Y-%m-%d') if row['msg_date'] else 'Unknown'
            date_labels.append(d_str)
            date_marks.append(row['marks_count'])
            date_attendance.append(row['att_count'])
            date_table.append({
                'date': d_str,
                'unique_students': row['unique_students'],
                'marks': row['marks_count'],
                'attendance': row['att_count'],
                'total_sent': row['total_sent'],
                'delivered': row['delivered_count'],
                'read': row['read_count'],
                'failed': row['failed_count'],
            })
        # Sort date table descending for display
        date_table_desc = sorted(date_table, key=lambda x: x['date'], reverse=True)

        # 2. Section Stacked Bar & Section Table
        sec_rows = (
            sent_qs.values('section_id', 'group_id')
            .annotate(
                marks_count=Count('id', filter=Q(category=PendingMessage.CATEGORY_MARKS)),
                att_count=Count('id', filter=Q(category=PendingMessage.CATEGORY_ATTENDANCE)),
                total_sent=Count('id'),
                unique_students=Count('student_id', distinct=True)
            )
            .order_by('group_id', 'section_id')
        )

        section_map = {s.pk: s for s in set(m.section for m in sent_qs.select_related('section') if m.section)}
        group_map = {g.pk: g for g in set(m.group for m in sent_qs.select_related('group') if m.group)}

        section_labels = []
        section_marks = []
        section_attendance = []
        section_table = []

        for row in sec_rows:
            sec_obj = section_map.get(row['section_id'])
            grp_obj = group_map.get(row['group_id'])
            label = get_section_label(sec_obj, grp_obj)

            section_labels.append(label)
            section_marks.append(row['marks_count'])
            section_attendance.append(row['att_count'])

            section_table.append({
                'group_code': grp_obj.code if grp_obj else 'Unassigned',
                'section_name': str(sec_obj) if sec_obj else 'Unassigned',
                'marks': row['marks_count'],
                'attendance': row['att_count'],
                'total_sent': row['total_sent'],
                'unique_students': row['unique_students'],
            })

        # Sort section table by group code, section name
        section_table = sorted(section_table, key=lambda x: (x['group_code'], x['section_name']))

        # 3. Doughnut Exclusive Status Buckets
        read_count = total_read
        delivered_unread = sent_qs.filter(status=PendingMessage.STATUS_DELIVERED).count()
        sent_only = sent_qs.filter(status=PendingMessage.STATUS_SENT).count()
        failed_count = total_failed
        queued_count = total_queued

        status_doughnut = {
            'labels': ['Read', 'Delivered (Unread)', 'Sent Only', 'Failed', 'Queued'],
            'data': [read_count, delivered_unread, sent_only, failed_count, queued_count],
        }

        # 4. Doughnut Category Split
        category_doughnut = {
            'labels': ['Marks', 'Attendance'],
            'data': [total_marks, total_attendance],
        }

        # 5. Students Receiving Multiple Messages (>1 sent message)
        multi_students_qs = (
            sent_qs.values('student_id', 'student__name', 'student__admission_number')
            .annotate(
                marks_count=Count('id', filter=Q(category=PendingMessage.CATEGORY_MARKS)),
                att_count=Count('id', filter=Q(category=PendingMessage.CATEGORY_ATTENDANCE)),
                total_sent=Count('id')
            )
            .filter(total_sent__gt=1)
            .order_by('-total_sent', 'student__name')
        )
        total_multi_students = multi_students_qs.count()
        multi_students_list = list(multi_students_qs[:100])

        tab_data = {
            'charts': {
                'date_bar': {'labels': date_labels, 'marks': date_marks, 'attendance': date_attendance},
                'section_bar': {'labels': section_labels, 'marks': section_marks, 'attendance': section_attendance},
                'status_doughnut': status_doughnut,
                'category_doughnut': category_doughnut,
            },
            'date_table': date_table_desc,
            'section_table': section_table,
            'multi_students': multi_students_list,
            'total_multi_students': total_multi_students,
        }

    elif tab in ('marks', 'attendance'):
        target_cat = PendingMessage.CATEGORY_MARKS if tab == 'marks' else PendingMessage.CATEGORY_ATTENDANCE
        cat_sent_qs = sent_qs.filter(category=target_cat)

        cat_total_sent = cat_sent_qs.count()
        cat_unique_students = cat_sent_qs.values('student_id').distinct().count()
        cat_msgs_per_student = round(cat_total_sent / cat_unique_students, 2) if cat_unique_students > 0 else 0.0
        cat_delivered = cat_sent_qs.filter(status__in=[PendingMessage.STATUS_DELIVERED, PendingMessage.STATUS_READ]).count()
        cat_read = cat_sent_qs.filter(status=PendingMessage.STATUS_READ).count()
        cat_failed = cat_sent_qs.filter(status=PendingMessage.STATUS_FAILED).count()

        breakdown_rows = (
            cat_sent_qs.values('msg_date', 'section_id', 'group_id')
            .annotate(
                students_contacted=Count('student_id', distinct=True),
                messages_sent=Count('id'),
                delivered_count=Count('id', filter=Q(status__in=[PendingMessage.STATUS_DELIVERED, PendingMessage.STATUS_READ])),
                read_count=Count('id', filter=Q(status=PendingMessage.STATUS_READ)),
                failed_count=Count('id', filter=Q(status=PendingMessage.STATUS_FAILED))
            )
            .order_by('-msg_date', 'group_id', 'section_id')
        )

        section_map = {s.pk: s for s in set(m.section for m in cat_sent_qs.select_related('section') if m.section)}
        group_map = {g.pk: g for g in set(m.group for m in cat_sent_qs.select_related('group') if m.group)}

        breakdown_table = []
        for row in breakdown_rows:
            sec_obj = section_map.get(row['section_id'])
            grp_obj = group_map.get(row['group_id'])
            d_str = row['msg_date'].strftime('%Y-%m-%d') if row['msg_date'] else 'Unknown'

            breakdown_table.append({
                'date': d_str,
                'group_code': grp_obj.code if grp_obj else 'Unassigned',
                'section_name': str(sec_obj) if sec_obj else 'Unassigned',
                'students_contacted': row['students_contacted'],
                'messages_sent': row['messages_sent'],
                'delivered': row['delivered_count'],
                'read': row['read_count'],
                'failed': row['failed_count'],
            })

        tab_data = {
            'summary': {
                'total_sent': cat_total_sent,
                'unique_students': cat_unique_students,
                'msgs_per_student': cat_msgs_per_student,
                'delivered': cat_delivered,
                'read': cat_read,
                'failed': cat_failed,
            },
            'breakdown_table': breakdown_table,
        }

    return {
        'summary': summary,
        'tab_data': tab_data,
    }
