#!/bin/bash
set -e
cd "/Users/saikumar/Library/Mobile Documents/com~apple~CloudDocs/srinri_sai"

echo "Staging the Students page bulk-select/edit changes..."
git add students/views.py students/urls.py templates/students/list.html templates/students/bulk_edit.html

echo "Committing..."
git commit -m "Make admission number editable (with uniqueness checks) and stage tap-to-edit table changes until Save Edits is pressed"

echo "Pushing..."
git push origin main

echo "Done. Now go trigger a Manual Deploy on Render (or wait for auto-deploy)."
