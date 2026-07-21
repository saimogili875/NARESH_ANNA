#!/bin/bash
set -e
cd "/Users/saikumar/Library/Mobile Documents/com~apple~CloudDocs/srinri_sai"

echo "Staging the individual fee amount feature..."
git add fees/views.py fees/urls.py templates/fees/assign_type_individual.html templates/fees/manage_types.html

echo "Committing..."
git commit -m "Add per-student hand-typed fee amounts for custom fee types (e.g. 2nd Year Previous Year Dues), alongside the existing bulk same-amount-per-section option"

echo "Pushing..."
git push origin main

echo "Done. Now go trigger a Manual Deploy on Render (or wait for auto-deploy)."
