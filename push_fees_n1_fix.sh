#!/bin/bash
set -e
cd "/Users/saikumar/Library/Mobile Documents/com~apple~CloudDocs/srinri_sai"

echo "Staging the Fees page performance fix..."
git add fees/views.py

echo "Committing..."
git commit -m "Fix /fees/ timing out with 300+ students: replace per-student DB queries (600-1200+ round trips) with bulk fetches and prefetching (~10 queries total regardless of student count)"

echo "Pushing..."
git push origin main

echo "Done. Now go trigger a Manual Deploy on Render (or wait for auto-deploy)."
