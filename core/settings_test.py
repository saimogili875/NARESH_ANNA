from .settings import *
import tempfile

SECRET_KEY = 'test-dummy-secret-key-for-testing-only'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

MEDIA_ROOT = tempfile.mkdtemp()

# Disable silk and keep axes disabled
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'silk']
MIDDLEWARE = [m for m in MIDDLEWARE if 'axes' not in m.lower() and 'silk' not in m.lower()]
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

AXES_ENABLED = False
ENABLE_PROFILING = False
SILENCED_SYSTEM_CHECKS = ['axes.W002', 'axes.W003']

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
