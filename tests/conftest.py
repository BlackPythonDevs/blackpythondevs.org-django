import pytest
from django.core.management import call_command


@pytest.fixture(autouse=True)
def _disable_rate_limits(settings):
    """allauth's signup/code throttles would otherwise trip mid-test."""
    settings.ACCOUNT_RATE_LIMITS = {}


@pytest.fixture
def site(db):
    """A bootstrapped site: page tree, settings, and seeded snippets."""
    call_command("bootstrap_site", verbosity=0)
    from home.models import HomePage

    return HomePage.objects.get()
