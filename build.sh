#!/usr/bin/env bash
# exit on error
set -o errexit

# 1. Install dependencies
pip install -r requirements.txt

# 2. Collect static files (required by WhiteNoise manifest storage)
python manage.py collectstatic --no-input

# 3. Run migrations to create database tables
python manage.py migrate

# 4. Superuser creation from environment variables (optional)
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists() or User.objects.create_superuser(username='$DJANGO_SUPERUSER_USERNAME', password='$DJANGO_SUPERUSER_PASSWORD')"
fi