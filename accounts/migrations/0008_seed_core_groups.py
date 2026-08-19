from django.db import migrations

def seed_core_groups(apps, schema_editor):
    AcademicYear = apps.get_model('accounts', 'AcademicYear')
    Group = apps.get_model('accounts', 'Group')
    Section = apps.get_model('accounts', 'Section')

    active_year = AcademicYear.objects.filter(is_active=True).first()

    DEFAULT_GROUPS = [
        {'name': 'MPC', 'code': 'MPC', 'subjects_text': 'Maths, Physics, Chemistry'},
        {'name': 'BiPC', 'code': 'BIPC', 'subjects_text': 'Biology, Physics, Chemistry'},
        {'name': 'CEC', 'code': 'CEC', 'subjects_text': 'Civics, Economics, Commerce'},
        {'name': 'MEC', 'code': 'MEC', 'subjects_text': 'Maths, Economics, Commerce'},
    ]

    for dg in DEFAULT_GROUPS:
        grp, grp_created = Group.objects.get_or_create(
            code=dg['code'],
            defaults={
                'name': dg['name'],
                'subjects_text': dg['subjects_text'],
                'academic_year': active_year
            }
        )
        if grp_created or not Section.objects.filter(group=grp).exists():
            Section.objects.get_or_create(group=grp, year='1', name='A', defaults={'academic_year': active_year})
            Section.objects.get_or_create(group=grp, year='2', name='A', defaults={'academic_year': active_year})

def reverse_seed(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0007_loginlog'),
    ]

    operations = [
        migrations.RunPython(seed_core_groups, reverse_code=reverse_seed),
    ]
