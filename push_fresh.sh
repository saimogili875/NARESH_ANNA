#!/bin/bash
set -e
cd "/Users/saikumar/Library/Mobile Documents/com~apple~CloudDocs/srinri_sai"

echo "Step 1: wiping old git history..."
rm -rf .git

echo "Step 2: starting a brand new repo..."
git init
git branch -m main
git remote add origin https://github.com/saimogili875/NARESH_ANNA.git

echo "Step 3: staging all current code..."
git add -A
git commit -m "Fresh start: dynamic fee types, section-wise fee assignment, exam bug fixes, attendance table update, fixed college name in receipts/reports"

echo "Step 4: force-pushing to GitHub (replaces everything currently there)..."
git push -f origin main

echo "Done."
