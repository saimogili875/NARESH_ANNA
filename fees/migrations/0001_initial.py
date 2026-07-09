# Generated migration for fees app

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
            name='StudentFee',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_fee', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('academic_year', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.academicyear')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fees', to='students.student')),
            ],
            options={
                'unique_together': {('student', 'academic_year')},
            },
        ),
        migrations.CreateModel(
            name='FeePayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('payment_date', models.DateField()),
                ('payment_mode', models.CharField(
                    choices=[('cash', 'Cash'), ('upi', 'UPI'), ('dd', 'Demand Draft'), ('cheque', 'Cheque'), ('neft', 'NEFT/RTGS')],
                    default='cash',
                    max_length=10,
                )),
                ('receipt_number', models.CharField(max_length=30, unique=True)),
                ('collected_by', models.CharField(blank=True, max_length=100)),
                ('remarks', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('student_fee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='fees.studentfee')),
            ],
        ),
    ]
