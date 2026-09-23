from pathlib import Path
from decouple import config
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file into os.environ
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='srinri.in,www.srinri.in,localhost,127.0.0.1').split(',') + ['.onrender.com', 'localhost', '127.0.0.1']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'core',
    'axes',
    'accounts',
    'students',
    'attendance',
    'marks',
    'fees.apps.FeesConfig',
    'faculty',
    'reports',
    'whatsapp',
    'sai',
    'misc',
    'captcha',
]

MIDDLEWARE = [
    'core.middleware.IPWhitelistMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'accounts.middleware.SessionExpiryMiddleware',
    'axes.middleware.AxesMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'accounts.middleware.FacultyAccessMiddleware',
    'accounts.middleware.ActivityLogMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# --- Database Configuration (PostgreSQL / Supabase with SQLite fallback for local dev) ---
DB_ENGINE = config('DB_ENGINE', default='')
DB_HOST = config('DB_HOST', default='')
DB_NAME = config('DB_NAME', default='')
DB_USER = config('DB_USER', default='')
DB_PASSWORD = config('DB_PASSWORD', default='')
DB_PORT = config('DB_PORT', default='5432')
DATABASE_URL = config('DATABASE_URL', default='')

if DATABASE_URL:
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    }
elif DB_HOST and DB_NAME:
    DATABASES = {
        'default': {
            'ENGINE': DB_ENGINE or 'django.db.backends.postgresql',
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASSWORD,
            'HOST': DB_HOST,
            'PORT': DB_PORT,
            'CONN_MAX_AGE': 600,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
WHITENOISE_MANIFEST_STRICT = config('WHITENOISE_MANIFEST_STRICT', default=False, cast=bool)

# --- Cloud Storage (AWS S3) Configuration for Media Files ---
AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='')
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')
AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='ap-south-1')
AWS_S3_CUSTOM_DOMAIN = config('AWS_S3_CUSTOM_DOMAIN', default='')
AWS_LOCATION = config('AWS_LOCATION', default='media')

HAS_STORAGES = False
try:
    import storages  # noqa: F401
    HAS_STORAGES = True
except ImportError:
    HAS_STORAGES = False

if HAS_STORAGES and AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_STORAGE_BUCKET_NAME:
    if 'storages' not in INSTALLED_APPS:
        INSTALLED_APPS.append('storages')
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    AWS_QUERYSTRING_AUTH = False
    
    DEFAULT_FILE_STORAGE = 'storages.backends.s3.S3Storage'
    
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "access_key": AWS_ACCESS_KEY_ID,
                "secret_key": AWS_SECRET_ACCESS_KEY,
                "bucket_name": AWS_STORAGE_BUCKET_NAME,
                "region_name": AWS_S3_REGION_NAME,
                "location": AWS_LOCATION,
                "custom_domain": AWS_S3_CUSTOM_DOMAIN or None,
                "querystring_auth": False,
            },
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
    
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/'
    else:
        MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/{AWS_LOCATION}/'
    MEDIA_ROOT = BASE_DIR / 'media'
else:
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'
    
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Centralized WhatsApp Config ---
WHATSAPP_BATCH_SIZE = config('WHATSAPP_BATCH_SIZE', default=50, cast=int)

# --- Logging Configuration (Persistent File Log & Console) ---
LOGS_DIR = BASE_DIR / 'logs'
os.makedirs(LOGS_DIR, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'whatsapp_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'whatsapp_sender.log',
            'maxBytes': 5 * 1024 * 1024,  # 5 MB max
            'backupCount': 3,  # Keep 3 backups
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'whatsapp_sender': {
            'handlers': ['console', 'whatsapp_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}


# --- Meta WhatsApp Cloud API Config ---
META_WHATSAPP_TOKEN = config('META_WHATSAPP_TOKEN', default='')
META_WHATSAPP_PHONE_ID = config('META_WHATSAPP_PHONE_ID', default='')
META_WEBHOOK_VERIFY_TOKEN = config('META_WEBHOOK_VERIFY_TOKEN', default='')
META_APP_SECRET = config('META_APP_SECRET', default='')
WHATSAPP_CRON_SECRET = config('WHATSAPP_CRON_SECRET', default='')
META_TEMPLATE_ABSENCE = config('META_TEMPLATE_ABSENCE', default='absence_alert')
META_TEMPLATE_EXAM_MARKS = config('META_TEMPLATE_EXAM_MARKS', default='marks_template')
MARKS_TEMPLATE_HAS_SUBJECTS = config('MARKS_TEMPLATE_HAS_SUBJECTS', default=False, cast=bool)
META_TEMPLATE_FACULTY_ABSENCE = config('META_TEMPLATE_FACULTY_ABSENCE', default='faculty_absence')
META_TEMPLATE_GENERAL = config('META_TEMPLATE_GENERAL', default='general_notification')
WHATSAPP_DEFAULT_LANGUAGE = config('WHATSAPP_DEFAULT_LANGUAGE', default='en')
WHATSAPP_DAILY_DISPATCH_TIME = config('WHATSAPP_DAILY_DISPATCH_TIME', default='10:30')

# --- Gemini AI Multilingual Config ---
GEMINI_API_KEY = config('GEMINI_API_KEY', default='')


SITE_BASE_URL = config('SITE_BASE_URL', default='http://127.0.0.1:8000')

# --- IP Whitelisting ---
_raw_ips = os.environ.get('ALLOWED_CLIENT_IPS', '')
ALLOWED_CLIENT_IPS = [ip.strip() for ip in _raw_ips.split(',') if ip.strip()]
IP_WHITELIST_EXEMPT_PATHS = ['/healthz', '/whatsapp/webhook/']

# Render terminates TLS at its proxy
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# --- Authentication Backends (axes + default) ---
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# --- django-axes: Login Lockout ---
AXES_FAILURE_LIMIT = config('AXES_FAILURE_LIMIT', default=5, cast=int)
AXES_COOLOFF_TIME = config('AXES_COOLOFF_TIME', default=1, cast=float)  # hours
AXES_LOCKOUT_PARAMETERS = [["ip_address", "username"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = None  # We handle lockout in the login view
AXES_WHITELIST_CALLABLE = 'accounts.views.axes_admin_whitelist'

# --- Email (for lockout alerts) ---
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER or 'noreply@srinri.edu')
LOCKOUT_NOTIFY_EMAIL = 'mogilisaikumar875@gmail.com'

# --- Attendance Time Lock ---
ATTENDANCE_CUTOFF_HOUR = 18
ATTENDANCE_CUTOFF_MINUTE = 0

# --- Fixed-Duration Session Expiry ---
# Session expires 120 minutes (2 hours) after login_time, regardless of activity.
SESSION_EXPIRY_FACULTY_MINUTES = 120   # Faculty accounts (2 hours)
SESSION_EXPIRY_OTHER_MINUTES = 120     # Admin / accounts / superuser (2 hours)
SESSION_COOKIE_AGE = 7200              # 2 hours (7200 seconds)

# --- WhatsApp Batch Sender ---
WHATSAPP_BATCH_SIZE = config('WHATSAPP_BATCH_SIZE', default=50, cast=int)

