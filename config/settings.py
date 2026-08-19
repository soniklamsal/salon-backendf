"""
Django settings for the Salon backend.

This project exists to make every band of the Next.js landing page editable from
an admin screen instead of a source file. It is deliberately small: SQLite, one
API namespace (`/api/v1/`), and a Jazzmin admin whose menu is ordered to match
the page top-to-bottom.
"""

from pathlib import Path

from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


# The fallback is fine for local development only; .env.example explains how to
# generate a real one. DEBUG=False with the fallback still in place is refused
# at the bottom of this file.
SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")

DEBUG = env_bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Used to build absolute media URLs when no request is in hand.
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", "").rstrip("/")


INSTALLED_APPS = [
    # Must precede django.contrib.admin — Jazzmin overrides the admin templates.
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "cloudinary_storage",
    "cloudinary",
    # Abstract base models only, so no tables. Listed so its AppConfig.ready()
    # can connect the content-cache invalidation signals.
    "common",
    "core",
    "sections",
    "bookings",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # Must sit above CommonMiddleware so preflight responses get the headers.
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# SQLite is the development database and is fine for one person editing content.
# It is not fine in production: every booking submission is a write, and SQLite
# takes a database-wide lock for each one. Set DATABASE_URL to a postgres:// URL
# and this switches over; leave it unset and nothing changes.
#
# Parsed by hand rather than with dj-database-url — it is fifteen lines and this
# is the only place that needs it.
def _database_from_url(url: str) -> dict:
    from urllib.parse import unquote, urlparse

    parsed = urlparse(url)
    engines = {
        "postgres": "django.db.backends.postgresql",
        "postgresql": "django.db.backends.postgresql",
        "mysql": "django.db.backends.mysql",
        "sqlite": "django.db.backends.sqlite3",
    }
    engine = engines.get(parsed.scheme)
    if engine is None:
        raise RuntimeError(f"DATABASE_URL: unsupported scheme {parsed.scheme!r}")

    config = {
        "ENGINE": engine,
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
        # Reuse connections for ten minutes. Connection setup is the
        # dominant cost of a small read like the homepage payload.
        "CONN_MAX_AGE": int(env("DB_CONN_MAX_AGE", "600")),
        "CONN_HEALTH_CHECKS": True,
    }

    # MySQL-specific settings for production compatibility
    if engine == "django.db.backends.mysql":
        config["OPTIONS"] = {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        }

    return config


DATABASE_URL = env("DATABASE_URL")

DATABASES = {
    "default": (
        _database_from_url(DATABASE_URL)
        if DATABASE_URL
        else {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {
                # SQLite takes a lock over the whole database for a write and,
                # by default, gives up the instant it finds one held — so two
                # staff approving bookings at the same moment produce
                # "database is locked" rather than one simply going second.
                # Waiting is what Postgres does; this makes SQLite do it too.
                "timeout": 20,
                # Take the write lock when the transaction opens rather than
                # upgrading to it mid-way. `approve()` reads the last order ID
                # and then writes, and an upgrade at that point is the case
                # SQLite cannot queue and has to fail.
                # Note: transaction_mode requires Django 5.1+, commented for 5.0
                # "transaction_mode": "IMMEDIATE",
            },
        }
    )
}

# --- Cache -----------------------------------------------------------------
# Backs the content cache in `common/cache.py`. The published endpoints are
# read-mostly -- the salon edits copy in the admin a few times a week and the
# site serves it thousands of times -- so the same payload is rebuilt from a
# dozen queries on every request without this.
#
# Local memory by default, which needs nothing installed and survives a cPanel
# host with no Redis. It is per-process, so each worker warms its own copy;
# that costs a little duplicated work and is still far cheaper than no cache.
# Set REDIS_URL and every worker shares one, which is what a busier deploy
# wants. Entries are invalidated by version bump, not by expiry (see
# `common/cache.py`), so the timeout is only a backstop against a stale key
# nobody bumped.
REDIS_URL = env("REDIS_URL")

CACHES = {
    "default": (
        {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "TIMEOUT": 600,
        }
        if REDIS_URL
        else {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "salon-content",
            "TIMEOUT": 600,
            # The whole cached set is a handful of JSON payloads; the default
            # 300 would never be reached, but a bound is cheap insurance.
            "OPTIONS": {"MAX_ENTRIES": 500},
        }
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Payment screenshots are financial records, so they must never sit in
# MEDIA_ROOT — that folder is served directly by the web server and anything in
# it is world-readable to whoever guesses the path. They go here instead, which
# nothing serves, and reach the customer through an authorising view. See
# common/storage.py.
PRIVATE_MEDIA_ROOT = Path(env("PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private-media")))

# Caps on what an anonymous booking can upload. The booking endpoint takes a
# file from anyone with no account, so an unbounded upload is a bill and a disk
# somebody else gets to choose the size of.
MAX_UPLOAD_BYTES = int(env("MAX_UPLOAD_MB", "8")) * 1024 * 1024
# Anything larger than this spills to a temp file instead of being held in RAM.
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
# The whole request body, not just one file. Multipart uploads are exempt from
# this in Django, which is why MAX_UPLOAD_BYTES is enforced per-file as well.
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_BYTES + (1024 * 1024)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200
# Guards against decompression bombs: a small file that expands to gigapixels.
MAX_UPLOAD_PIXELS = int(env("MAX_UPLOAD_PIXELS", str(50_000_000)))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# --- Cloudinary ------------------------------------------------------------
# Admin uploads (hero art, service photos, barber headshots, payment
# screenshots) go to Cloudinary instead of the local `media/` folder as soon as
# all three credentials are present. Without them the local folder is still
# used, so the project keeps running on a fresh clone with no account.
#
# Only `default` is switched: static files stay with WhiteNoise, which is what
# collectstatic and the manifest hashing expect.
CLOUDINARY_STORAGE = {
    "CLOUD_NAME": env("CLOUDINARY_CLOUD_NAME"),
    "API_KEY": env("CLOUDINARY_API_KEY"),
    "API_SECRET": env("CLOUDINARY_API_SECRET"),
}

USE_CLOUDINARY = all(CLOUDINARY_STORAGE.values())

# Optional. Cloudinary's token-based authentication add-on, which makes a
# signed URL *expire*. Without it, signed URLs for payment screenshots are
# still unguessable and still refused without a signature — they just do not
# time out. Set this if the plan includes the add-on.
CLOUDINARY_AUTH_TOKEN_KEY = env("CLOUDINARY_AUTH_TOKEN_KEY")

if USE_CLOUDINARY:
    STORAGES["default"] = {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Pins the suite to local storage so it never uploads to the live Cloudinary
# account. See common/testing.py.
TEST_RUNNER = "common.testing.SalonTestRunner"


# --- API -------------------------------------------------------------------

REST_FRAMEWORK = {
    # The site content is public by definition — it is what the landing page
    # renders. Write access is the admin's job, so every viewset here is
    # read-only and the only writable endpoints (bookings, contact) are
    # explicitly opted in.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    # Only applies to views that set a throttle_scope; the read endpoints do not.
    # `bookings` is tighter than `submissions` because each one carries a file.
    # `bookings` is tighter than `submissions` because each one carries a file.
    # The two read scopes are deliberately generous -- they exist to stop
    # somebody hammering an endpoint for free, not to ration normal use. A
    # customer refreshing their status page a dozen times must never meet them.
    "DEFAULT_THROTTLE_RATES": {
        "submissions": "20/hour",
        "bookings": "10/hour",
        "my-bookings": "240/hour",
        "screenshot": "600/hour",
    },
    "UNAUTHENTICATED_USER": None,
    # Every list endpoint here is a published-content list that is small today,
    # which is exactly the condition that stops being true without anyone
    # noticing. Page size is generous enough that the frontend's existing
    # single-request assumptions still hold.
    "DEFAULT_PAGINATION_CLASS": "common.pagination.DefaultPagination",
    "PAGE_SIZE": 100,
    "EXCEPTION_HANDLER": "common.exceptions.exception_handler",
}

# --- Clerk (optional) ------------------------------------------------------
# Set CLERK_ISSUER (e.g. https://your-app.clerk.accounts.dev) once the Clerk
# app exists. Until then verification is off and bookings are recorded without
# an account, which is what keeps the site working before the keys are added.
CLERK_ISSUER = os.environ.get("CLERK_ISSUER", "")
CLERK_JWKS_URL = os.environ.get("CLERK_JWKS_URL", "")
# Backend API key. Only used to LIST accounts for the admin; never sent to
# the browser and never logged.
CLERK_SECRET_KEY = os.environ.get("CLERK_SECRET_KEY", "")
# Origins allowed to have minted a session token this API will accept, checked
# against the token's `azp` claim. Comma-separated; empty switches the check
# off, which is the pre-existing behaviour and what keeps an unconfigured
# deployment working. Set it to the frontend origin in production -- it is what
# stops a Clerk token issued for a different site being replayed here.
CLERK_AUTHORIZED_PARTIES = env("CLERK_AUTHORIZED_PARTIES", "")

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
)
# Next.js server components fetch server-side (no Origin header, CORS not
# involved); this is for client components and the browsable API.
CORS_ALLOW_CREDENTIALS = False

CSRF_TRUSTED_ORIGINS = [
    origin for origin in CORS_ALLOWED_ORIGINS if origin.startswith("https://")
]


# --- Email (SMTP) ----------------------------------------------------------
# Off by default. Without EMAIL_HOST_USER and EMAIL_HOST_PASSWORD, mail is
# written to stdout instead of sent, which is what a fresh clone and the test
# suite want -- the same shape as the Cloudinary block above: the presence of
# credentials is the switch, there is nothing else to turn on.
#
# The defaults are Gmail's. .env.example spells out the App Password step,
# which is the part that is not optional: Google stopped accepting an account
# password over SMTP, so the ordinary password here always fails.
#
# Everything here reads through `email_env`, not `env`: a key present in .env
# but left blank ("EMAIL_PORT=") reaches os.environ as an empty string, which
# beats a default that is only applied when the key is missing entirely. For
# an optional block that ships pre-listed in .env.example, blank has to mean
# unset or the documented defaults are the one thing nobody gets.
def email_env(name: str, default: str = "") -> str:
    return env(name).strip() or default


def email_env_bool(name: str, default: bool) -> bool:
    return env_bool(name, default) if env(name).strip() else default


EMAIL_HOST = email_env("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(email_env("EMAIL_PORT", "587"))

EMAIL_HOST_USER = env("EMAIL_HOST_USER").strip()
# Google shows an App Password as four groups of four ("abcd efgh ijkl mnop")
# and people paste it that way. The spaces are presentation, not part of the
# secret, and leaving them in produces an authentication failure that looks
# like a wrong password.
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD").replace(" ", "")

# 587 is STARTTLS, 465 is implicit TLS. Deriving both from the port means the
# common case needs no further settings; either can still be forced by env.
EMAIL_USE_TLS = email_env_bool("EMAIL_USE_TLS", EMAIL_PORT == 587)
EMAIL_USE_SSL = email_env_bool("EMAIL_USE_SSL", EMAIL_PORT == 465)

if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise RuntimeError(
        "EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be on. Use TLS with port "
        "587 or SSL with port 465, not both."
    )

# Django's default is no timeout at all, so an unreachable SMTP host hangs the
# request thread until the OS gives up. Every send here happens inside a web
# request, so it is capped.
EMAIL_TIMEOUT = int(email_env("EMAIL_TIMEOUT", "10"))

# Whether *.env alone* could send. The admin screen may supply credentials
# instead, so this is not the same question as "can this site send mail" --
# common.email_config.active_config() answers that one.
EMAIL_CONFIGURED = bool(EMAIL_HOST_USER and EMAIL_HOST_PASSWORD)

# Not Django's SMTP backend directly. This one re-reads the SMTP settings on
# every send, so a password typed into the admin takes effect on the next
# booking instead of the next restart, and it falls back to printing to the
# console when neither the admin nor .env has credentials. See
# common/email_backend.py.
EMAIL_BACKEND = email_env("EMAIL_BACKEND") or "common.email_backend.ConfiguredEmailBackend"

# Gmail rewrites the envelope sender to the authenticated account regardless of
# what is set here, so anything other than that account (or an alias verified
# under Gmail's "Send mail as") shows up as a mismatch to spam filters.
DEFAULT_FROM_EMAIL = email_env("DEFAULT_FROM_EMAIL") or (
    EMAIL_HOST_USER or "webmaster@localhost"
)
# Where Django's own error mail comes from, if ADMINS is ever set.
SERVER_EMAIL = email_env("SERVER_EMAIL") or DEFAULT_FROM_EMAIL

# Notifications go out on a background thread so the customer's booking is not
# waiting on Gmail. Turn it off to send inline -- simpler to debug, and the
# only sane setting if this ever moves behind a real task queue.
EMAIL_NOTIFY_ASYNC = email_env_bool("EMAIL_NOTIFY_ASYNC", True)

# The salon's own inbox -- who gets told when a booking or an enquiry arrives.
# Defaults to the sending account, which is the usual case for a single Gmail.
SALON_NOTIFY_EMAILS = env_list("SALON_NOTIFY_EMAILS") or (
    [EMAIL_HOST_USER] if EMAIL_HOST_USER else []
)


# --- Admin -----------------------------------------------------------------

from config.jazzmin import JAZZMIN_SETTINGS, JAZZMIN_UI_TWEAKS  # noqa: E402,F401


# --- Production guardrails -------------------------------------------------

if not DEBUG:
    if SECRET_KEY == "dev-only-insecure-key-change-me":
        raise RuntimeError(
            "DJANGO_SECRET_KEY is still the development fallback. Set a real "
            "one in .env before running with DJANGO_DEBUG=False."
        )
    if DATABASES["default"]["ENGINE"].endswith("sqlite3"):
        raise RuntimeError(
            "Refusing to run with DJANGO_DEBUG=False on SQLite. Every booking "
            "submission is a write and SQLite locks the whole database for "
            "each one. Set DATABASE_URL to a MySQL or PostgreSQL URL."
        )
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_REFERRER_POLICY = "same-origin"

    # Behind a reverse proxy terminating TLS, Django only knows the request was
    # HTTPS if the proxy says so. Without this, SECURE_SSL_REDIRECT sees every
    # request as plain HTTP and redirects forever.
    if env_bool("TRUST_PROXY_SSL_HEADER", True):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    # Both default on but are switched off by env var, because the first deploy
    # of a new domain is often served over plain HTTP for a few minutes and
    # HSTS is not something you can take back from a browser that cached it.
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
    # Preloading is deliberately opt-in. Getting onto the preload list is easy
    # and getting off it takes months.
    SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)


# --- Logging ---------------------------------------------------------------
# Without this, a failure in the booking path in production goes nowhere at
# all. Everything goes to stdout, which is what a process manager or container
# runtime collects; no file paths to get wrong and no log rotation to forget.
#
# Nothing here logs request bodies. The booking payload contains a name, phone
# number, address and a payment screenshot, and none of that belongs in a log.

LOG_LEVEL = env("DJANGO_LOG_LEVEL", "DEBUG" if DEBUG else "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
        "simple": {"format": "{levelname} {message}", "style": "{"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple" if DEBUG else "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        # Pinned, not inherited: `django` at DEBUG makes this echo every SQL
        # statement, which buries everything else in development.
        "django.db.backends": {
            "handlers": ["console"],
            "level": env("DJANGO_SQL_LOG_LEVEL", "INFO").upper(),
            "propagate": False,
        },
        # Every 500 that reaches a client.
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        # Ours: the API error handler, booking failures, Clerk verification.
        "api": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "bookings": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "common": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
