from django.db import migrations
from django.conf import settings
from django.db.models import F


def backfill_analytics_fields(apps, schema_editor):
    PendingMessage = apps.get_model('whatsapp', 'PendingMessage')

    exam_templates = {
        getattr(settings, 'META_TEMPLATE_EXAM_MARKS', 'exam_marks'),
        'marks_template',
        'exam_marks',
    }
    absence_templates = {
        getattr(settings, 'META_TEMPLATE_ABSENCE', 'absence_alert'),
        'absence_alert',
    }

    # Backfill category for existing student messages
    PendingMessage.objects.filter(student__isnull=False, template_name__in=exam_templates).update(category='MARKS')
    PendingMessage.objects.filter(student__isnull=False, template_name__in=absence_templates).update(category='ATTENDANCE')

    # Backfill section and group from student's current section for student rows with section_id IS NULL
    student_messages = PendingMessage.objects.filter(student__isnull=False, section__isnull=True).select_related('student__section')
    updates = []
    for msg in student_messages.iterator():
        if msg.student and msg.student.section:
            msg.section_id = msg.student.section_id
            msg.group_id = msg.student.section.group_id
            updates.append(msg)
    if updates:
        PendingMessage.objects.bulk_update(updates, ['section', 'group'], batch_size=500)

    # sent_at = created_at for existing rows with status in ('sent', 'delivered', 'read')
    PendingMessage.objects.filter(status__in=['sent', 'delivered', 'read'], sent_at__isnull=True).update(sent_at=F('created_at'))


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0008_add_analytics_fields'),
    ]

    operations = [
        migrations.RunPython(backfill_analytics_fields, reverse_code=migrations.RunPython.noop),
    ]
