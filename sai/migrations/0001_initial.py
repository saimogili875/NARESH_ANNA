# Generated migration for LabPerformanceReport model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('students', '0003_alter_student_apaar_id_alter_student_second_mobile_and_more'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='LabPerformanceReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_of_report', models.DateField(auto_now_add=True)),
                ('jee_best_score', models.IntegerField(blank=True, null=True)),
                ('jee_avg_score', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('jee_mocks_attended', models.IntegerField(blank=True, null=True)),
                ('eamcet_best_score', models.IntegerField(blank=True, null=True)),
                ('eamcet_avg_score', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('eamcet_mocks_attended', models.IntegerField(blank=True, null=True)),
                ('ipe_score', models.IntegerField(blank=True, null=True)),
                ('ipe_percentage', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('weekly_avg_score', models.IntegerField(blank=True, null=True)),
                ('remarks', models.TextField(blank=True, help_text='General remarks about performance')),
                ('academic_year', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.academicyear')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lab_reports', to='students.student')),
            ],
            options={
                'ordering': ['-date_of_report'],
            },
        ),
    ]
