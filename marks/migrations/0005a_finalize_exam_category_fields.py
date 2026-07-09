# Split out of migration 0005 on purpose: Postgres refuses to run ALTER TABLE
# on a table that had rows UPDATEd (via RunPython) earlier in the *same*
# transaction ("cannot ALTER TABLE ... because it has pending trigger events").
# 0005 renames the old string columns out of the way, adds the new nullable FK
# columns, and backfills them via RunPython. This migration runs in its own
# transaction (guaranteed committed separately from 0005) and just drops the
# now-unused old string columns and tightens the new FK columns to non-null.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marks', '0005_examcategory_examtype_subject_alter_exam_category_and_more'),
    ]

    operations = [
        # Drop the old string columns now that data has been migrated
        migrations.RemoveField(model_name='exam', name='category_old'),
        migrations.RemoveField(model_name='exam', name='exam_type_old'),
        migrations.RemoveField(model_name='examsubjectmaxmark', name='subject_old'),
        migrations.RemoveField(model_name='mark', name='subject_old'),

        # Tighten the new FK fields to match the real model (not nullable)
        migrations.AlterField(
            model_name='exam',
            name='category',
            field=models.ForeignKey(help_text='Decides which subjects appear on the marks entry screen.', on_delete=django.db.models.deletion.CASCADE, to='marks.examcategory'),
        ),
        migrations.AlterField(
            model_name='exam',
            name='exam_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='marks.examtype'),
        ),
        migrations.AlterField(
            model_name='examsubjectmaxmark',
            name='subject',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='marks.subject'),
        ),
        migrations.AlterField(
            model_name='mark',
            name='subject',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='marks.subject'),
        ),

        # Restore unique_together now that 'subject' refers to the new FK field again
        migrations.AlterUniqueTogether(name='examsubjectmaxmark', unique_together={('exam', 'subject')}),
        migrations.AlterUniqueTogether(name='mark', unique_together={('student', 'exam', 'subject')}),

        migrations.CreateModel(
            name='GroupCategoryConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='marks.examcategory')),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.group')),
                ('subjects', models.ManyToManyField(to='marks.subject')),
            ],
            options={
                'unique_together': {('group', 'category')},
            },
        ),
    ]
