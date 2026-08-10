"""
Django settings for neighborhood_tracker project.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY: In production, set the DJANGO_SECRET_KEY environment variable
# instead of relying on the fallback below. Never commit a real secret key.
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-change-this-key-in-production-1234567890'
)

# SECURITY: Set DJANGO_DEBUG=False in production (via environment variable).
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'

# SECURITY: Restrict this to your real domain(s) in production, e.g.
# DJANGO_ALLOWED_HOSTS=neighborhoodtracker.gov.in,www.neighborhoodtracker.gov.in
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '*').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'cloudinary_storage',
    'django.contrib.staticfiles',
    'cloudinary',
    'issues',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'neighborhood_tracker.urls'

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
                'issues.context_processors.notifications_processor',
            ],
        },
    },
]

WSGI_APPLICATION = 'neighborhood_tracker.wsgi.application'

# Development uses SQLite with zero configuration. For production, set
# DJANGO_DB_ENGINE=postgresql and the DJANGO_DB_* variables below.
if os.environ.get('DJANGO_DB_ENGINE') == 'postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DJANGO_DB_NAME', 'neighborhood_tracker'),
            'USER': os.environ.get('DJANGO_DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DJANGO_DB_PASSWORD', ''),
            'HOST': os.environ.get('DJANGO_DB_HOST', 'localhost'),
            'PORT': os.environ.get('DJANGO_DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('en', 'English'),
    ('ta', 'தமிழ்'),
]
LOCALE_PATHS = [BASE_DIR / 'locale']

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
# WhiteNoise serves static files directly from Django in production (Render/Railway
# don't run a separate nginx/Apache) - compressed + hashed filenames for caching.

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ---------------------------------------------------------------------------
# Media storage (uploaded photos) - Render's filesystem is EPHEMERAL, meaning
# any file saved locally (issue photos, completion photos) is lost on the
# next deploy or restart. Cloudinary provides free, permanent cloud storage
# for these uploads instead.
#
# Setup: create a free account at https://cloudinary.com, then from your
# Cloudinary Dashboard copy the Cloud Name, API Key, and API Secret into
# these three environment variables on Render:
#   DJANGO_CLOUDINARY_CLOUD_NAME
#   DJANGO_CLOUDINARY_API_KEY
#   DJANGO_CLOUDINARY_API_SECRET
#
# Until these are set, uploads fall back to local disk storage - fine for
# local development, but photos won't survive a Render redeploy.
# ---------------------------------------------------------------------------
CLOUDINARY_CLOUD_NAME = os.environ.get('DJANGO_CLOUDINARY_CLOUD_NAME', '')
CLOUDINARY_API_KEY = os.environ.get('DJANGO_CLOUDINARY_API_KEY', '')
CLOUDINARY_API_SECRET = os.environ.get('DJANGO_CLOUDINARY_API_SECRET', '')

if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    CLOUDINARY_STORAGE = {
        'CLOUD_NAME': CLOUDINARY_CLOUD_NAME,
        'API_KEY': CLOUDINARY_API_KEY,
        'API_SECRET': CLOUDINARY_API_SECRET,
    }
    STORAGES = {
        "default": {
            "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Logging - Django's default config only prints tracebacks to console when
# DEBUG=True, which means production errors (DEBUG=False) are normally
# invisible in server logs. This makes 500 errors show their full traceback
# in Render/Railway/any host's log viewer regardless of DEBUG.
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'issue_list'
LOGOUT_REDIRECT_URL = 'issue_list'

# ---------------------------------------------------------------------------
# Caching - in-process memory cache, zero extra setup (no Redis/Memcached
# server required). Used to cache expensive dashboard aggregate queries.
# For a multi-server production deployment, swap this for Redis/Memcached.
# ---------------------------------------------------------------------------
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'neighborhood-tracker-cache',
        'TIMEOUT': 120,  # 2 minutes - dashboards refresh often enough without hammering the DB
    }
}

# ---------------------------------------------------------------------------
# Email - sends the citizen a confirmation email + complaint PDF from the
# government address on report submission (see report_issue in views.py).
#
# IMPORTANT SETUP (Gmail blocks your normal password for this):
#   1. Log in to koraigaltn@gmail.com
#   2. Turn on 2-Step Verification: https://myaccount.google.com/security
#   3. Create an "App Password": https://myaccount.google.com/apppasswords
#   4. Set it as the DJANGO_EMAIL_PASSWORD environment variable (NOT the normal
#      Gmail password - App Passwords are a 16-character code Google generates).
#
# Until DJANGO_EMAIL_PASSWORD is set, emails print to the terminal instead of
# actually sending - so report submission never breaks even before email is
# configured, which matters for a live demo.
# ---------------------------------------------------------------------------
EMAIL_HOST_USER = os.environ.get('DJANGO_EMAIL_USER', 'koraigaltn@gmail.com')
EMAIL_HOST_PASSWORD = os.environ.get('DJANGO_EMAIL_PASSWORD', '')
DEFAULT_FROM_EMAIL = f"Kuraigal.TN <{EMAIL_HOST_USER}>"

if EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'smtp.gmail.com'
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_TIMEOUT = 10  # seconds - fail fast instead of hanging the whole request if Gmail is slow/unreachable
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ---------------------------------------------------------------------------
# Session hardening
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True          # JS can never read the session cookie
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7   # 7 days
CSRF_COOKIE_HTTPONLY = False            # must stay False - the JS chatbot/AJAX calls need to read it
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# ---------------------------------------------------------------------------
# Upload limits - reject unexpectedly huge uploads before they hit disk.
# ---------------------------------------------------------------------------
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB request body cap
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB per file

# ---------------------------------------------------------------------------
# Production security headers (harmless in dev - only take effect when
# DEBUG=False via the DJANGO_DEBUG env var, e.g. behind HTTPS in production).
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SSL_REDIRECT', 'True') == 'True'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_REFERRER_POLICY = 'same-origin'
