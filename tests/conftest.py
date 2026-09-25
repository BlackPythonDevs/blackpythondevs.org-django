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
    """A minimal, routable site: just a home page as the site root.

    Most tests only need a page tree to hang pages off and route URLs
    through — not the full production tree, settings, and seeded snippets.
    Running `bootstrap_site` for every test made it the dominant cost of the
    suite (roughly 1s/test, on almost every test). Tests that exercise
    `bootstrap_site` itself, or rely on specific pages/snippets/accounts it
    seeds, should request `bootstrapped_site` instead (or override this
    fixture locally, as test_membership.py's TestMembershipPage does for the
    one page it needs beyond Home).
    """
    from wagtail.models import Page, Site

    from home.models import HomePage

    root = Page.objects.get(depth=1)
    wagtail_site = Site.objects.filter(is_default_site=True).first()

    # Retire Wagtail's stub page the same way bootstrap_site does, so a home
    # page can take its slot.
    stub = Page.objects.filter(depth=2, slug="home").first()
    if stub and wagtail_site and wagtail_site.root_page_id == stub.pk:
        wagtail_site.root_page = root
        wagtail_site.save()
    if stub:
        stub.delete()

    home = HomePage(title="Black Python Devs", slug="home")
    root.add_child(instance=home)
    home.save_revision().publish()

    if wagtail_site:
        wagtail_site.root_page = home
        wagtail_site.hostname = wagtail_site.hostname or "localhost"
        wagtail_site.save()
    else:
        Site.objects.create(hostname="localhost", port=80, root_page=home, is_default_site=True)

    return home


@pytest.fixture
def bootstrapped_site(db):
    """The real, fully-seeded site: page tree, settings, and seeded snippets.

    For tests that exercise `bootstrap_site` itself, or depend on specific
    pages, snippets, or accounts that only it seeds (foundational supporters,
    leaders, sponsors, the 2027 summit, ...).
    """
    call_command("bootstrap_site", verbosity=0)
    from home.models import HomePage

    return HomePage.objects.get()
