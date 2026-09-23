"""Base settings shared by every environment."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-me-in-production")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

# CARTO now requires an API key on all basemap tile requests.
CARTO_API_KEY = env("CARTO_API_KEY", default="")

INSTALLED_APPS = [
    # Project apps
    "core",
    "home",
    "blog",
    "events",
    "sponsorships",
    "ambassadors",
    "nominations",
    "elections",
    "notifications",
    "communities",
    "community_messages",
    "users",
    # Wagtail
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.contrib.settings",
    "wagtail.contrib.table_block",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",
    "neapolitan",
    "django_countries",
    # allauth
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.discord",
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "widget_tweaks",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]

ROOT_URLCONF = "bpd.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "wagtail.contrib.settings.context_processors.settings",
                "core.context_processors.site_context",
            ],
        },
    },
]

WSGI_APPLICATION = "bpd.wsgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://bpd:bpd@localhost:5432/bpd",
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)

# ── Valkey (Redis protocol) ───────────────────────────────────────────────
VALKEY_URL = env("VALKEY_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": VALKEY_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": "bpd",
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

AUTH_USER_MODEL = "users.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── django-allauth ────────────────────────────────────────────────────────
# Passwordless: members sign up with an email address only, then log in with a
# one-time code emailed to them. Omitting password1/password2 from
# SIGNUP_FIELDS is what makes signup passwordless, so LOGIN_BY_CODE_ENABLED
# must stay on — without it an account with no password could never log in.
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*"]
ACCOUNT_LOGIN_BY_CODE_ENABLED = True
ACCOUNT_LOGIN_BY_CODE_TIMEOUT = env.int("ACCOUNT_LOGIN_BY_CODE_TIMEOUT", default=600)
ACCOUNT_LOGIN_BY_CODE_MAX_ATTEMPTS = 3

# Passwordless signup: if the email already has an account, email that member a
# login code and drop them on the code-entry page, rather than allauth's default
# "reset your password" notice (there are no passwords here). See users/forms.py.
ACCOUNT_FORMS = {"signup": "users.forms.SignupForm"}

ACCOUNT_EMAIL_VERIFICATION = env("ACCOUNT_EMAIL_VERIFICATION", default="mandatory")
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True
# Without this, a signup whose confirmation code expires or gets lost has no
# "Request new code" button on the confirm-email page at all (it defaults to
# 0 allowed resends) -- their only way back in is to cancel out of the stage
# and request a fresh sign-in code from the login page instead.
ACCOUNT_EMAIL_VERIFICATION_SUPPORTS_RESEND = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[Black Python Devs] "

# Signup is the main abuse surface when anyone can request a code by email.
ACCOUNT_RATE_LIMITS = {
    "login_failed": "5/5m",
    "signup": "10/h",
    "request_login_code": "3/5m/ip,1/1m/key",
    "confirm_email": "3/5m",
}

# Discord is a *connection*, never a sign-in method. Email codes are the only
# way in. SocialAccountAdapter.is_open_for_signup blocks account creation via
# Discord, and email authentication is off so an unlinked Discord account can
# never be matched to an existing user by email address.
SOCIALACCOUNT_AUTO_SIGNUP = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = False
SOCIALACCOUNT_PROVIDERS = {
    "discord": {
        # `identify` names the account; `guilds.join` lets the bot add the
        # member to the server with their messaging role.
        "SCOPE": ["identify", "guilds.join"],
    },
}
# OAuth app credentials from the Discord developer portal. When both are set,
# register the app in settings (no DB SocialApp needed) so the connect flow
# lights up; when absent, the member page degrades gracefully.
DISCORD_CLIENT_ID = env("DISCORD_CLIENT_ID", default="")
DISCORD_CLIENT_SECRET = env("DISCORD_CLIENT_SECRET", default="")
if DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET:
    SOCIALACCOUNT_PROVIDERS["discord"]["APPS"] = [
        {
            "client_id": DISCORD_CLIENT_ID,
            "secret": DISCORD_CLIENT_SECRET,
        }
    ]
SOCIALACCOUNT_ADAPTER = "users.adapters.SocialAccountAdapter"

LOGIN_REDIRECT_URL = "/members/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"
ACCOUNT_SIGNUP_REDIRECT_URL = "/members/"
ACCOUNT_ADAPTER = "users.adapters.AccountAdapter"

# ── Discord ───────────────────────────────────────────────────────────────
# Connecting a Discord account adds the member to the community server and
# grants the role that permits messaging. All three must be set for that to
# happen; with any unset, connecting only links the account and members follow
# the plain invite link instead.
DISCORD_GUILD_ID = env("DISCORD_GUILD_ID", default="")
DISCORD_BOT_TOKEN = env("DISCORD_BOT_TOKEN", default="")
DISCORD_MEMBER_ROLE_ID = env("DISCORD_MEMBER_ROLE_ID", default="")
DISCORD_INVITE_URL = env("DISCORD_INVITE_URL", default="https://discord.gg/XUc3tFqCT3")

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Wagtail ───────────────────────────────────────────────────────────────
WAGTAIL_SITE_NAME = "Black Python Devs"
WAGTAILADMIN_BASE_URL = env("WAGTAILADMIN_BASE_URL", default="http://localhost:8000")
WAGTAILDOCS_EXTENSIONS = ["csv", "docx", "key", "odt", "pdf", "pptx", "rtf", "txt", "xlsx", "zip"]
WAGTAILIMAGES_IMAGE_MODEL = "core.CustomImage"
WAGTAIL_ENABLE_UPDATE_CHECK = False
WAGTAILSEARCH_BACKENDS = {
    "default": {
        "BACKEND": "wagtail.search.backends.database",
    }
}

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@blackpythondevs.org")
