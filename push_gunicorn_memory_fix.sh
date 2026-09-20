#!/bin/bash
set -e
cd "/Users/saikumar/Library/Mobile Documents/com~apple~CloudDocs/srinri_sai"

echo "Staging the gunicorn memory-safety fix..."
git add Procfile

echo "Committing..."
git commit -m "Fix Render worker OOM kills: use gthread workers with threads instead of extra processes, recycle workers periodically via max-requests, and use /dev/shm for the worker tmp dir"

echo "Pushing..."
git push origin main

echo "Done. Now go trigger a Manual Deploy on Render (or wait for auto-deploy)."
