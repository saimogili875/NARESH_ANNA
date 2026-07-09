#!/usr/bin/env bash
# exit on error
set -o errexit

# 1. Install dependencies
pip install -r requirements.txt

# 2. Run migrations to create database tables
python manage.py migrate

# 3. First admin account
echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(username='SriNri@2026').exists() or User.objects.create_superuser(username='SriNri@2026', password='Ather@8435')" | python manage.py shell

# 4. Second admin account (Spaces replaced with underscores)
echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(username='MOGILI_SAI_KUMAR').exists() or User.objects.create_superuser(username='MOGILI_SAI_KUMAR', password='srinidhi@123')" | python manage.py shell