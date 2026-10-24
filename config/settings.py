"""
Configuración del HRMS.

Todos los valores sensibles o dependientes del entorno se leen de variables de
entorno, de modo que el mismo código corre en desarrollo (SQLite) y en
producción (PostgreSQL en Render, Railway, Fly.io, un VPS, etc.).
"""

import os
import sys
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "si", "on")


def env_list(name, default=""):
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


DEBUG = env_bool("DJANGO_DEBUG", True)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("Definí la variable de entorno DJANGO_SECRET_KEY en producción.")
    SECRET_KEY = "dev-insegura-solo-para-desarrollo"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
# Render expone el hostname público en esta variable.
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    CSRF_TRUSTED_ORIGINS.append("https://" + os.environ["RENDER_EXTERNAL_HOSTNAME"])

# GitHub Codespaces: habilita la URL pública del puerto reenviado (p. ej. desde un iPad).
if os.environ.get("CODESPACE_NAME"):
    _cs_domain = os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
    ALLOWED_HOSTS.append(f".{_cs_domain}")
    CSRF_TRUSTED_ORIGINS.append(f"https://{os.environ['CODESPACE_NAME']}-8000.{_cs_domain}")
    # El proxy de Codespaces reescribe el encabezado Origin a https://localhost:8000.
    CSRF_TRUSTED_ORIGINS.append("https://localhost:8000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.core",
    "apps.empleados",
    "apps.licencias",
    "apps.asistencia",
    "apps.reclutamiento",
    "apps.onboarding",
    "apps.anuncios",
    "apps.reportes",
    "apps.pagos",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.HolidaySyncMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.hrms",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}
# Cada operación se graba completa o no se graba nada (sin estados intermedios si la base falla a mitad de camino).
DATABASES["default"]["ATOMIC_REQUESTS"] = True

AUTH_USER_MODEL = "core.User"
AUTHENTICATION_BACKENDS = ["apps.core.backends.CaseInsensitiveModelBackend"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# Localización Argentina: formato $ 1.234.567,89 y fechas dd/mm/aaaa.
LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_I18N = True
USE_TZ = True
# Los importes se formatean con los filtros propios (ars, num); así los años y IDs no llevan punto de miles.
USE_THOUSAND_SEPARATOR = False

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

# Los archivos subidos (legajos, fotos, CVs) NO se sirven públicamente:
# se descargan a través de una vista que valida permisos (core.views.media_protegida).
MEDIA_URL = "/archivos/"
MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", BASE_DIR / "media"))

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024
HRMS_MAX_UPLOAD_MB = int(os.environ.get("HRMS_MAX_UPLOAD_MB", "10"))

# Actualización automática semanal de feriados (se desactiva en los tests).
HRMS_HOLIDAY_AUTO_SYNC = env_bool("HRMS_HOLIDAY_AUTO_SYNC", "test" not in sys.argv)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sesión: expira a las 8 h o al cerrar el navegador.
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = env_bool("DJANGO_SESSION_EXPIRE_AT_CLOSE", True)

EMAIL_BACKEND = os.environ.get("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("DJANGO_EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "rrhh@localhost")

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "3600"))
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
}
