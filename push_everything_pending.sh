#!/bin/bash
set -e
cd "/Users/saikumar/Library/Mobile Documents/com~apple~CloudDocs/srinri_sai"

echo "Staging all pending changes (Students bulk-edit + Fee individual-amount features)..."
git add \
  students/views.py students/urls.py templates/students/list.html templates/students/bulk_edit.html \
  fees/views.py fees/urls.py templates/fees/manage_types.html templates/fees/assign_type_individual.html

echo "Committing..."
git commit -m "Students page: select mode, bulk delete/move/change-details, tap-to-edit with staged save, editable admission number. Fees: per-student hand-typed fee amounts for custom fee types."

echo "Pushing..."
git push origin main

echo "Done. Now go trigger a Manual Deploy on Render (or wait for auto-deploy)."
