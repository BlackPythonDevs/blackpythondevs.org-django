"""Checks on the infrastructure wiring: cache, storages, and static files."""

import pytest
from django.conf import settings
from django.core.cache import cache

pytestmark = pytest.mark.django_db


def test_valkey_cache_round_trip():
    cache.set("bpd-test-key", "value", 30)
    assert cache.get("bpd-test-key") == "value"
    cache.delete("bpd-test-key")


def test_static_files_served_by_whitenoise():
    assert "whitenoise.middleware.WhiteNoiseMiddleware" in settings.MIDDLEWARE
    assert settings.STORAGES["staticfiles"]["BACKEND"].startswith("whitenoise.storage")


def test_media_uses_local_filesystem_in_dev():
    assert settings.STORAGES["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage"


def test_production_switches_media_to_s3_when_bucket_configured(monkeypatch):
    """Production keeps local media until a bucket is set, then uses S3."""
    import importlib

    monkeypatch.setenv("SECRET_KEY", "test-only")
    monkeypatch.setenv("AWS_STORAGE_BUCKET_NAME", "some-bucket")

    production = importlib.import_module("bpd.settings.production")
    importlib.reload(production)

    assert production.STORAGES["default"]["BACKEND"] == "storages.backends.s3.S3Storage"
    assert production.STORAGES["staticfiles"]["BACKEND"] == (
        "whitenoise.storage.CompressedManifestStaticFilesStorage"
    )


def test_robots_and_sitemap(client, site):
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Disallow: /cms/" in robots.content.decode()
    assert client.get("/sitemap.xml").status_code == 200


def test_sessions_are_stored_in_cache():
    assert settings.SESSION_ENGINE == "django.contrib.sessions.backends.cache"
