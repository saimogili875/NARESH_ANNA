#!/bin/bash
set -e
cd "/Users/saikumar/Library/Mobile Documents/com~apple~CloudDocs/srinri_sai"

echo "Staging the users-page access change..."
git add accounts/decorators.py accounts/views.py templates/base.html

echo "Committing..."
git commit -m "Restrict /users/ to Django superusers only and remove Account Users link from sidebar"

echo "Pushing..."
git push origin main

echo "Done. Now go trigger a Manual Deploy on Render (or wait for auto-deploy)."
