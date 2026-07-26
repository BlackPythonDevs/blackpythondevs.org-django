"""Local development settings."""

from .base import *  # noqa: F403
from .base import BASE_DIR, INSTALLED_APPS, MIDDLEWARE, env

DEBUG = True
SECRET_KEY = env("SECRET_KEY", default="django-insecure-dev-only-not-for-production")
ALLOWED_HOSTS = ["*"]

# Media lives on the local filesystem in development; production swaps in S3.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Non-manifest storage in dev so a missing entry doesn't 500 the page.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# WhiteNoise serves static files in dev too, so behaviour matches production.
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True

# Sign-in codes and verification codes print to the console in development.
# ACCOUNT_EMAIL_VERIFICATION stays "mandatory" (from base) because
# verification-by-code requires it, and with passwordless signup the emailed
# code *is* the verification step.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

INSTALLED_APPS = INSTALLED_APPS + ["wagtail.contrib.styleguide", "debug_toolbar"]
MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE
INTERNAL_IPS = ["127.0.0.1"]


def _show_toolbar(request):
    """Docker's bridge network gives the host a changing IP, so INTERNAL_IPS is
    unreliable; key off DEBUG instead. Read it from django.conf at call time so
    the test runner's DEBUG=False actually turns the toolbar off."""
    from django.conf import settings as _settings

    return _settings.DEBUG


DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": _show_toolbar}

try:
    from .local import *  # noqa: F403
except ImportError:
    pass

_ = BASE_DIR
