# Split out of migration 0005 on purpose: 0005 adds the new nullable FK columns
# (which queues deferred index-creation SQL that Postgres flushes at the end of
# that migration's transaction). If the data backfill below ran in that same
# migration, the UPDATE statements here would leave "pending trigger events" that
# clash with 0005's deferred index creation. Keeping this as its own migration
# guarantees a real COMMIT happens between "add columns" and "backfill data".
#
# 0005a (which runs after this one) drops the old string columns and tightens
# the new FK columns to non-null, now that they're fully populated.

from django.db import migrations


CATEGORY_LABELS = {
    'ipe': 'IPE',
    'jee': 'JEE Main',
    'eamcet': 'EAPCET',
    'eamcet_jee': 'EAMCET / JEE Main',
    'neet': 'NEET',
    'cuet': 'CUET',
}

EXAM_TYPE_LABELS = {
    'unit1': 'Unit Test 1',
    'unit2': 'Unit Test 2',
    'quarterly': 'Quarterly Exam',
    'halfyearly': 'Half-Yearly Exam',
    'prefinal': 'Pre-Final Exam',
    'final': 'Final Exam',
    'custom': 'Custom Exam',
}


def backfill_fk_data(apps, schema_editor):
    Exam = apps.get_model('marks', 'Exam')
    ExamSubjectMaxMark = apps.get_model('marks', 'ExamSubjectMaxMark')
    Mark = apps.get_model('marks', 'Mark')
    ExamCategory = apps.get_model('marks', 'ExamCategory')
    ExamType = apps.get_model('marks', 'ExamType')
    Subject = apps.get_model('marks', 'Subject')

    # --- Exam.category: legacy string -> ExamCategory row ---
    cat_ids = {}
    for val in Exam.objects.values_list('category_old', flat=True).distinct():
        key = val or 'ipe'
        if key not in cat_ids:
            label = CATEGORY_LABELS.get(key, key.upper())
            cat, _ = ExamCategory.objects.get_or_create(name=label)
            cat_ids[key] = cat.id
        Exam.objects.filter(category_old=val).update(category_id=cat_ids[key])

    # --- Exam.exam_type: legacy string -> ExamType row ---
    type_ids = {}
    for val in Exam.objects.values_list('exam_type_old', flat=True).distinct():
        key = val or 'custom'
        if key not in type_ids:
            label = EXAM_TYPE_LABELS.get(key, key.title())
            et, _ = ExamType.objects.get_or_create(name=label)
            type_ids[key] = et.id
        Exam.objects.filter(exam_type_old=val).update(exam_type_id=type_ids[key])

    # --- Subject: shared lookup for both ExamSubjectMaxMark.subject and Mark.subject ---
    subj_ids = {}

    def subject_id_for(raw_name):
        name = (raw_name or '').strip() or 'Unknown'
        if name not in subj_ids:
            s, _ = Subject.objects.get_or_create(name=name)
            subj_ids[name] = s.id
        return subj_ids[name]

    for val in ExamSubjectMaxMark.objects.values_list('subject_old', flat=True).distinct():
        ExamSubjectMaxMark.objects.filter(subject_old=val).update(subject_id=subject_id_for(val))

    for val in Mark.objects.values_list('subject_old', flat=True).distinct():
        Mark.objects.filter(subject_old=val).update(subject_id=subject_id_for(val))


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('marks', '0005_examcategory_examtype_subject_alter_exam_category_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_fk_data, noop_reverse),
    ]
