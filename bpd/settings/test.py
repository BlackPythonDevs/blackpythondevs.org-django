"""Test settings: the pytest suite runs against FakeValkey, not a real server.

Referenced only by pyproject.toml's ``DJANGO_SETTINGS_MODULE`` — never import
it from application code. It imports base (not dev) so the debug toolbar and
dev-only conveniences stay out of the test run.

CACHES keeps django_redis as the backend but swaps its connection factory for
one that hands out fakeredis clients backed by a single in-process
FakeServer, so no Valkey container (or network) is needed to run tests. The
server is shared process-wide so every cache backend instance in the worker
sees the same data; tests/conftest.py clears it between tests.
"""

import fakeredis
from django_redis.pool import ConnectionFactory

from .base import *  # noqa: F403
from .base import env

_fake_server = fakeredis.FakeServer()


class FakeConnectionFactory(ConnectionFactory):
    """Hand django_redis a fakeredis client instead of a real connection."""

    def connect(self, url: str):
        self.make_connection_params(url)  # validate the options as usual
        return fakeredis.FakeRedis(server=_fake_server)


CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://fakevalkey/0",  # never dialled; kept for OPTIONS parity
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_FACTORY": "bpd.settings.test.FakeConnectionFactory",
        },
        "KEY_PREFIX": "bpd",
    }
}

SECRET_KEY = env("SECRET_KEY", default="django-insecure-test-only-not-for-production")

# Like dev: non-manifest WhiteNoise storage (and finders, not the collected
# staticfiles dir) so tests don't need `collectstatic` to have run.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True
