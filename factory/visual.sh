#!/bin/sh
# The software factory's buildfile for screenshot evidence on pull requests
# (https://github.com/kjaymiller/factory — the [visual] section of its
# factory.toml points here). The factory asks which steps exist and runs each
# one inside the workcell, from the checkout root, against the cell's
# throwaway Postgres (there may be no Valkey: see write_settings):
#
#   steps   print the steps this file provides (this list)
#   setup   migrate and seed the scratch database
#   serve   run the app on 127.0.0.1:8000 in the foreground; the factory
#           backgrounds it and waits for the URL to answer
#   auth    print one line, AUTH=name=value: a session cookie so pages behind
#           a login are photographed as themselves, not as the login page
#
# The screenshots show the change as a user would see it, so this file decides
# what that evidence looks like. In factory.toml it is extra_high: every change
# here is a pull request a person reads.
set -eu

# Settings for the photos only, written outside the checkout: the dev settings
# with the Django debug toolbar switched off, so it cannot be in the picture,
# and with no Valkey. A factory cell may not have one (Nevia cells don't), and
# dev keeps sessions in the Valkey cache, so the session `auth` makes would be
# lost. Sessions go to the scratch database instead, which `auth` and `serve`
# both read, and the cache is per-process memory.
SETTINGS=/tmp/shots-settings
export DJANGO_SETTINGS_MODULE=shots_settings
export PYTHONPATH="$SETTINGS"
export DEBUG=True
export ALLOWED_HOSTS=localhost,127.0.0.1
export CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000

write_settings() {
    mkdir -p "$SETTINGS"
    cat >"$SETTINGS/shots_settings.py" <<'PY'
from bpd.settings.dev import *
DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": lambda request: False}
SESSION_ENGINE = "django.contrib.sessions.backends.db"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PY
}

case "${1:-}" in
steps)
    printf '%s\n' setup serve auth
    ;;
setup)
    write_settings
    uv run python manage.py migrate --noinput
    uv run python manage.py bootstrap_site
    ;;
serve)
    write_settings
    exec uv run python manage.py runserver 127.0.0.1:8000 --noreload
    ;;
auth)
    # A throwaway superuser in the cell's own scratch database. Pages such as
    # /members/ redirect any user whose onboarding_completed_at is empty to
    # /onboarding/ (needs_onboarding in users/models.py), so it is set.
    write_settings
    uv run python manage.py shell -c '
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

u, _ = get_user_model().objects.get_or_create(
    username="factory-shots",
    defaults={"email": "shots@example.invalid", "is_staff": True, "is_superuser": True},
)
if not u.onboarding_completed_at:
    u.onboarding_completed_at = timezone.now()
    u.save(update_fields=["onboarding_completed_at"])
c = Client()
c.force_login(u)
print("AUTH=sessionid=" + c.cookies["sessionid"].value)
'
    ;;
*)
    echo "usage: sh factory/visual.sh {steps|setup|serve|auth}" >&2
    exit 2
    ;;
esac
