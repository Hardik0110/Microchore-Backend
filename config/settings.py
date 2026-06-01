import os
from pathlib import Path
from datetime import timedelta
from urllib.parse import urlparse
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = os.environ['SECRET_KEY']
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

ALLOWED_HOSTS = [host.strip() for host in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if host.strip()]

if not DEBUG:
    if (
        not SECRET_KEY
        or SECRET_KEY in ('changeme',)
        or SECRET_KEY.startswith('django-insecure')
        or len(SECRET_KEY) < 32
    ):
        raise ImproperlyConfigured('SECRET_KEY must be a strong random value (>=32 chars) in production.')
    if '*' in ALLOWED_HOSTS:
        raise ImproperlyConfigured('ALLOWED_HOSTS must not contain "*" in production.')
    _OWNED_WILDCARD_ALLOWLIST = {
        h.strip().lower()
        for h in os.getenv('ALLOWED_HOST_WILDCARD_ALLOWLIST', '').split(',')
        if h.strip()
    }
    for _h in ALLOWED_HOSTS:
        if _h.startswith('.') and _h.lower() not in _OWNED_WILDCARD_ALLOWLIST:
            raise ImproperlyConfigured(
                f'ALLOWED_HOSTS contains wildcard "{_h}" not in ALLOWED_HOST_WILDCARD_ALLOWLIST.'
            )

FRONTEND_BASE_URL = os.getenv('FRONTEND_BASE_URL', 'http://localhost:5173').rstrip('/')
BACKEND_BASE_URL = os.getenv('BACKEND_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'channels',

    'accounts',
    'projects',
    'submissions',
    'reviews',
    'earnings',
    'verification',
    'ai_detection',
    'monitoring',
    'company_admin',
    'workers',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

def _build_db_config():
    db_url = os.getenv('DATABASE_URL', '').strip()
    if not db_url:
        if not DEBUG:
            raise ImproperlyConfigured(
                'DATABASE_URL is required in production. SQLite cannot safely serve concurrent writers.'
            )
        return {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    parsed = urlparse(db_url)
    if parsed.scheme not in ('postgres', 'postgresql', 'postgresql+psycopg', 'postgresql+psycopg2'):
        raise ImproperlyConfigured(f'Unsupported DATABASE_URL scheme: {parsed.scheme!r}.')
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': (parsed.path or '').lstrip('/'),
        'USER': parsed.username or '',
        'PASSWORD': parsed.password or '',
        'HOST': parsed.hostname or '',
        'PORT': str(parsed.port) if parsed.port else '',
        'CONN_MAX_AGE': int(os.getenv('CONN_MAX_AGE', '60')),
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {'sslmode': os.getenv('DB_SSLMODE', 'require')},
    }


DATABASES = {'default': _build_db_config()}

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOW_ALL_ORIGINS = os.getenv('CORS_ALLOW_ALL_ORIGINS', 'False').lower() == 'true'
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',') if origin.strip()]

if not DEBUG and CORS_ALLOW_ALL_ORIGINS:
    raise ImproperlyConfigured('CORS_ALLOW_ALL_ORIGINS must be False in production.')

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True').lower() == 'true'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    X_FRAME_OPTIONS = 'DENY'

EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '25'))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'False').lower() == 'true'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False').lower() == 'true'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@microchore.local')
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '10'))

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'accounts.authentication.StatusAwareJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': os.getenv('THROTTLE_ANON', '60/min'),
        'user': os.getenv('THROTTLE_USER', '600/min'),
        'auth_signup': os.getenv('THROTTLE_AUTH_SIGNUP', '5/min'),
        'auth_login': os.getenv('THROTTLE_AUTH_LOGIN', '10/min'),
        'auth_logout': os.getenv('THROTTLE_AUTH_LOGOUT', '10/min'),
        'auth_refresh': os.getenv('THROTTLE_AUTH_REFRESH', '30/min'),
        'auth_google': os.getenv('THROTTLE_AUTH_GOOGLE', '10/min'),
        'email_verify_request': os.getenv('THROTTLE_EMAIL_VERIFY_REQUEST', '5/min'),
        'email_verify_confirm': os.getenv('THROTTLE_EMAIL_VERIFY_CONFIRM', '20/min'),
        'submission_create': os.getenv('THROTTLE_SUBMISSION_CREATE', '10/min'),
    },
}

MICROCHORE_ACTIVE_CLAIM_CAP = int(os.getenv('MICROCHORE_ACTIVE_CLAIM_CAP', '10'))

GOOGLE_OAUTH_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '')

YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY', '').strip()

APIFY_API_TOKEN = os.getenv('APIFY_API_TOKEN', '').strip()
APIFY_IG_PROFILE_ACTOR = os.getenv('APIFY_IG_PROFILE_ACTOR', 'apify~instagram-profile-scraper').strip()
APIFY_IG_COMMENT_ACTOR = os.getenv('APIFY_IG_COMMENT_ACTOR', 'apify~instagram-comment-scraper').strip()

JWT_SIGNING_KEY = os.getenv('JWT_SIGNING_KEY', '').strip() or SECRET_KEY

if not DEBUG and JWT_SIGNING_KEY == SECRET_KEY:
    raise ImproperlyConfigured(
        'JWT_SIGNING_KEY must be set to a distinct value from SECRET_KEY in production.'
    )

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': JWT_SIGNING_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',
}

REDIS_URL = os.getenv('REDIS_URL', '').strip()

if REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {'hosts': [REDIS_URL]},
        },
    }
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
        },
    }
else:
    if not DEBUG:
        raise ImproperlyConfigured(
            'REDIS_URL is required in production. InMemoryChannelLayer cannot serve multi-worker deployments.'
        )
    CHANNEL_LAYERS = {
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
    }
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'microchore-default',
        },
    }
