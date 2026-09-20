#!/bin/bash
set -e
cd "/Users/saikumar/Library/Mobile Documents/com~apple~CloudDocs/srinri_sai"

echo "Staging the import page instructions fix..."
git add templates/students/import.html

echo "Committing..."
git commit -m "Fix outdated Excel import instructions on the Import Students page to match the actual header-based import logic"

echo "Pushing..."
git push origin main

echo "Done. Now go trigger a Manual Deploy on Render (or wait for auto-deploy)."
