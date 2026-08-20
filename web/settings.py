from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

SECRET_KEY = os.environ.get("SPORTS_TODAY_SECRET_KEY", "local-development-only")
DEBUG = os.environ.get("SPORTS_TODAY_DEBUG", "1") == "1"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "SPORTS_TODAY_ALLOWED_HOSTS",
        "localhost,127.0.0.1,[::1],testserver,sports.sme327.com",
    ).split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "web",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "web.urls"
WSGI_APPLICATION = "web.wsgi.application"
ASGI_APPLICATION = "web.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "web" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["web.assets.asset_versions"]},
    }
]

# The current services own and query this schema directly. Django points at the same
# file so a later migration can adopt selected tables without copying today's data.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "database" / "sportshub.db",
        "OPTIONS": {"timeout": 30},
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Chicago"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "styles", BASE_DIR / "web" / "static"]
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "sports-today-web",
        "TIMEOUT": 120,
    }
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = os.environ.get("SPORTS_TODAY_SECURE_SSL", "0") == "1"
SECURE_HSTS_SECONDS = 31_536_000 if SECURE_SSL_REDIRECT else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_SSL_REDIRECT
SECURE_HSTS_PRELOAD = SECURE_SSL_REDIRECT
X_FRAME_OPTIONS = "DENY"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
