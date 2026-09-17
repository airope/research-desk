"""Local-first deployment settings. PostgreSQL is required for all domain writes."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Only the project .env is read; injected process values always take precedence.
load_dotenv(BASE_DIR / ".env", override=False, interpolate=False)
# An omitted profile keeps the workstation demo convenient. DEBUG=0 always
# activates production protections, including for existing launch scripts.
APP_ENV = os.getenv("APP_ENV", "production" if os.getenv("DEBUG") == "0" else "development")
if APP_ENV not in {"development", "test", "production"}:
    raise RuntimeError("APP_ENV must be development, test or production")
PRODUCTION = APP_ENV == "production" or os.getenv("DEBUG") == "0"
DEBUG = os.getenv("DEBUG", "0" if PRODUCTION else "1") == "1"
if PRODUCTION and DEBUG:
    raise RuntimeError("DEBUG must be disabled in production")
SECRET_KEY = os.getenv("SECRET_KEY", "local-demo-only-change-before-deployment")
if PRODUCTION and (
    len(SECRET_KEY) < 50
    or len(set(SECRET_KEY)) < 5
    or SECRET_KEY.startswith("django-insecure-")
    or SECRET_KEY == "local-demo-only-change-before-deployment"
):
    raise RuntimeError("Production requires a strong, unique SECRET_KEY (at least 50 characters)")
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "ALLOWED_HOSTS", "" if PRODUCTION else "localhost,127.0.0.1,testserver"
    ).split(",")
    if host.strip()
]
if PRODUCTION and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
    raise RuntimeError("Production requires explicit ALLOWED_HOSTS without a wildcard")
if PRODUCTION and os.getenv("PGPASSWORD", "") in {"", "srr-local-only"}:
    raise RuntimeError("Production requires a non-demo PGPASSWORD")
SESSION_COOKIE_SECURE = PRODUCTION
CSRF_COOKIE_SECURE = PRODUCTION
SECURE_SSL_REDIRECT = PRODUCTION
SECURE_HSTS_SECONDS = 31536000 if PRODUCTION else 0
# Subdomains and preload require domain ownership review; deliberately opt-in.
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("HSTS_INCLUDE_SUBDOMAINS", "0") == "1"
SECURE_HSTS_PRELOAD = os.getenv("HSTS_PRELOAD", "0") == "1"
# These are domain-wide commitments, not safe defaults for an application.
# Keep every other deployment warning enabled (including missing HSTS itself).
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]
# Enable only behind a trusted proxy that strips incoming forwarded headers.
if os.getenv("TRUST_HTTPS_PROXY", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()
]
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "records",
    "catalogues",
    "research",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "srr.middleware.RequestIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "srr.rate_limits.RateLimitMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "srr.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "srr.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("PGDATABASE", "srr"),
        "USER": os.getenv("PGUSER", "srr"),
        "PASSWORD": os.getenv("PGPASSWORD", "srr-local-only"),
        "HOST": os.getenv("PGHOST", "127.0.0.1"),
        "PORT": os.getenv("PGPORT", "55432"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"connect_timeout": 5},
    }
}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "records.api.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "120/min"},
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Scholarly Record Reconciliation API",
    "VERSION": "1.0.0",
    "DESCRIPTION": "Local metadata reconciliation. Scores are not probabilities.",
}
EXTERNAL_IMPORTS_ENABLED = os.getenv("EXTERNAL_IMPORTS_ENABLED", "0") == "1"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

# Personal workstation only. Never expose subscription-backed execution publicly.
RESEARCH_CODEX_ENABLED = os.getenv("RESEARCH_CODEX_ENABLED", "0") == "1"
if PRODUCTION and RESEARCH_CODEX_ENABLED:
    raise RuntimeError("Personal Codex execution is restricted to the local development profile")
RESEARCH_LOCAL_USER = os.getenv("RESEARCH_LOCAL_USER", "reviewer")

# Optional passage index; server-side credentials never reach model prompts.
RESEARCH_SEARCH_BACKEND = os.getenv("RESEARCH_SEARCH_BACKEND", "local")
RESEARCH_ELASTICSEARCH_URL = os.getenv("RESEARCH_ELASTICSEARCH_URL", "http://127.0.0.1:9200")
RESEARCH_ELASTICSEARCH_API_KEY = os.getenv("RESEARCH_ELASTICSEARCH_API_KEY", "")
RESEARCH_ELASTICSEARCH_READ_API_KEY = os.getenv("RESEARCH_ELASTICSEARCH_READ_API_KEY", "")
RESEARCH_ELASTICSEARCH_CA_CERTS = os.getenv("RESEARCH_ELASTICSEARCH_CA_CERTS", "")

# Shared PostgreSQL admission limits; reject invalid deployment overrides early.
for _setting, _default in {
    "RESEARCH_MAX_ACTIVE_PER_USER": 2,
    "RESEARCH_MAX_ACTIVE_GLOBAL": 50,
    "RESEARCH_DAILY_JOBS": 30,
    "RESEARCH_DAILY_DOSSIERS": 30,
    "USER_WRITES_PER_MINUTE": 60,
    "USER_SEARCHES_PER_MINUTE": 30,
    "LOGIN_ATTEMPTS_PER_WINDOW": 20,
}.items():
    _value = int(os.getenv(_setting, str(_default)))
    if _value < 1:
        raise RuntimeError(f"{_setting} must be a positive integer")
    globals()[_setting] = _value

# Model selection is operator-controlled, never inferred from whatever keys exist.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "codex").strip().lower() or "codex"
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip()
LLM_OUTPUT_MODE = os.getenv("LLM_OUTPUT_MODE", "").strip()
LLM_PROVIDER_KEYS = {
    name: os.getenv(name, "").strip()
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "MISTRAL_API_KEY",
        "DEEPSEEK_API_KEY",
        "GROQ_API_KEY",
        "XAI_API_KEY",
        "OPENROUTER_API_KEY",
    )
}
LLM_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "8192"))
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "180"))
if not 256 <= LLM_MAX_OUTPUT_TOKENS <= 32768 or not 1 <= LLM_TIMEOUT_SECONDS <= 180:
    raise RuntimeError("LLM output tokens must be 256–32768 and timeout 1–180 seconds")
