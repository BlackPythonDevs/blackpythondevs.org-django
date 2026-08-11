import copy

import pytest
from django.core.management import call_command


@pytest.fixture(autouse=True)
def _disable_rate_limits(settings):
    """allauth's signup/code throttles would otherwise trip mid-test.

    It has to be False, not {}: allauth builds its default limits and then does
    `ret.update(rls)`, so an empty dict merges nothing and leaves every throttle
    on. Only False short-circuits to no limits at all.

    This matters more than it looks. The throttle counters live in the Django
    cache, which here is a real Valkey shared with the running app, so the
    counts survive across tests and across whole runs — leaving this broken
    made /accounts/signup/ start returning 429 partway through a full suite.
    """
    settings.ACCOUNT_RATE_LIMITS = False


@pytest.fixture(autouse=True)
def _discord_unconfigured(settings):
    """Start every test from "Discord not set up", whatever .env says.

    Otherwise the suite passes or fails depending on the developer's ambient
    environment: with real credentials in .env, settings register a provider
    APP, the `discord_app` fixture adds a second one in the database, and
    allauth's provider lookup raises MultipleObjectsReturned. Tests that want
    Discord configured opt in with @override_settings or the fixture.

    SOCIALACCOUNT_PROVIDERS is deep-copied before editing: pytest-django only
    restores attributes it sees assigned, so mutating the nested dict in place
    would leak into every later test.
    """
    settings.DISCORD_GUILD_ID = ""
    settings.DISCORD_BOT_TOKEN = ""
    settings.DISCORD_MEMBER_ROLE_ID = ""

    providers = copy.deepcopy(settings.SOCIALACCOUNT_PROVIDERS)
    providers.get("discord", {}).pop("APPS", None)
    settings.SOCIALACCOUNT_PROVIDERS = providers


@pytest.fixture
def site(db):
    """A bootstrapped site: page tree, settings, and seeded snippets."""
    call_command("bootstrap_site", verbosity=0)
    from home.models import HomePage

    return HomePage.objects.get()
