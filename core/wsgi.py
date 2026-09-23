import os
from django.core.wsgi import get_wsgi_application
from django.conf import settings
from whitenoise import WhiteNoise

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

application = get_wsgi_application()

# WhiteNoise is restricted to static files (STATIC_ROOT) only.
# Private media files are served via authorized Django endpoints.

