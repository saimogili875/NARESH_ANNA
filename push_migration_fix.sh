#!/bin/bash
set -e
cd "/Users/saikumar/Library/Mobile Documents/com~apple~CloudDocs/srinri_sai"

echo "Fixing local migration history bookkeeping (safe, no schema/data changes)..."
python3 fix_local_migration_history.py

echo
echo "Staging the migration fix..."
git add marks/migrations/0005_examcategory_examtype_subject_alter_exam_category_and_more.py
git add marks/migrations/0005b_backfill_exam_category_fields.py
git add marks/migrations/0005a_finalize_exam_category_fields.py
git add marks/migrations/0006_remove_groupcategoryconfig_subjects_and_more.py
git add fix_local_migration_history.py

echo "Committing..."
git commit -m "Split marks migration 0005 into three: schema, data backfill, cleanup - avoids Postgres 'pending trigger events' error on both the RunPython and the deferred index-creation steps"

echo "Pushing..."
git push origin main

echo "Done. Now go trigger a Manual Deploy on Render (or wait for auto-deploy)."
