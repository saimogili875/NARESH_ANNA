from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='second_mobile',
            field=models.CharField(blank=True, max_length=15, help_text='Secondary contact number'),
        ),
        migrations.AddField(
            model_name='student',
            name='apaar_id',
            field=models.CharField(blank=True, max_length=20, verbose_name='APAAR ID',
                                   help_text='Academic Bank of Credits ID'),
        ),
        migrations.AddField(
            model_name='student',
            name='sport',
            field=models.CharField(blank=True, max_length=100,
                                   help_text='Sport activity the student participates in'),
        ),
    ]
