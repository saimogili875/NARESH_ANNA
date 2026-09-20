#!/bin/bash
set -e
cd "/Users/saikumar/Library/Mobile Documents/com~apple~CloudDocs/srinri_sai"

echo "Staging the cascade-delete fix..."
git add students/models.py students/migrations/0008_alter_student_academic_year_alter_student_section.py templates/accounts/groups.html

echo "Committing..."
git commit -m "Hard-delete students (and their attendance/marks/fee records) when their Section, Group, or Academic Year is deleted, instead of leaving them orphaned"

echo "Pushing..."
git push origin main

echo "Done. Now go trigger a Manual Deploy on Render (or wait for auto-deploy)."
