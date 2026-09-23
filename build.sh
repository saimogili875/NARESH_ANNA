#!/usr/bin/env bash
# exit on error
set -o errexit

# 1. Install dependencies
pip install -r requirements.txt

# 2. Collect static files (required by WhiteNoise manifest storage)
python manage.py collectstatic --no-input

# 3. Run migrations to create database tables
python manage.py migrate

# 4. Bootstrap admin accounts if environment variables are set
python manage.py bootstrap_admins