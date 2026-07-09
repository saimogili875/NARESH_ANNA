# Generated migration for marks app

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('students', '0001_initial'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Exam',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('exam_type', models.CharField(
                    choices=[
                        ('unit1', 'Unit Test 1'),
                        ('unit2', 'Unit Test 2'),
                        ('quarterly', 'Quarterly Exam'),
                        ('halfyearly', 'Half-Yearly Exam'),
                        ('prefinal', 'Pre-Final Exam'),
                        ('final', 'Final Exam'),
                        ('custom', 'Custom Exam'),
                    ],
                    max_length=20,
                )),
                ('custom_name', models.CharField(blank=True, help_text='Only for Custom Exam type', max_length=100)),
                ('date', models.DateField()),
                ('max_marks', models.IntegerField(default=100)),
                ('academic_year', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.academicyear')),
            ],
        ),
        migrations.CreateModel(
            name='Mark',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject', models.CharField(max_length=50)),
                ('marks_obtained', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('is_absent', models.BooleanField(default=False)),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='marks', to='marks.exam')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='marks', to='students.student')),
            ],
            options={
                'unique_together': {('student', 'exam', 'subject')},
            },
        ),
    ]
