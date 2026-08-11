"""Create the initial page tree, site settings, and snippets.

Idempotent: re-running updates what exists rather than duplicating it. Snippet
seed data comes from `fixtures/*.json`, carried over from the static site's
`_data/` directory.
"""

import datetime
import json
from pathlib import Path

from django.conf import settings as django_settings
from django.core.management.base import BaseCommand
from django.db import transaction
from wagtail.models import Page, Site

from blog.models import BlogIndexPage
from core.models import (
    Author,
    FooterSettings,
    FoundationalSupporter,
    Leader,
    NavigationItem,
    NavigationSettings,
    Partner,
    SocialSettings,
    Sponsor,
)
from events.models import EventIndexPage, EventPage
from sponsorships.models import SponsorshipRequest
from home.models import AboutPage, HomePage, MembershipPage, StandardPage, SupportPage

FIXTURES = Path(django_settings.BASE_DIR) / "fixtures"

NAV_ITEMS = [
    ("News", "/news/", "iconoir-journal-page"),
    ("About Us", "/about/", "iconoir-group"),
    ("Events", "/events/", "iconoir-calendar"),
    ("Donate", "/support/", "iconoir-donate"),
]

# "Become a Member" / "My account" is rendered separately in the header, since
# which one shows depends on whether the visitor is signed in.

SPONSORS = [
    ("GNOME Foundation", "https://foundation.gnome.org/", "images/gnome-foundation-blue.png"),
    ("Anaconda", "https://www.anaconda.com/", "images/2020_Anaconda_Logo_RGB_Corporate.png"),
    ("JetBrains", "https://www.jetbrains.com/", "images/jetbrains.webp"),
    ("Pydantic", "https://pydantic.dev/", "images/pydantic-lg.webp"),
    ("REVSYS", "https://www.revsys.com/", "images/revsys.webp"),
]

MEMBER_BENEFITS = [
    (
        "A global community",
        "Connect with Black Pythonistas across Africa, the Americas, Europe, and beyond.",
    ),
    (
        "Events and meetups",
        "Join our weekly coffee-and-code sessions and hear about events near you first.",
    ),
    (
        "Mentorship and support",
        "Find people further along the path, and support those coming up behind you.",
    ),
    (
        "Opportunities",
        "Hear about speaking slots, grants, and roles shared within the community.",
    ),
]

PRINCIPLES = [
    ("Diverse Leadership", "We build and support diverse leadership in Python globally."),
    (
        "Community Support",
        "We provide financial support for Python communities in Black communities, in predominantly "
        "Black spaces or spaces where there is a desire to improve accessibility to Black audiences.",
    ),
    (
        "A Louder Collective Voice",
        "We speak as a collective of Black leaders in the Python Community and how decisions impact "
        "developers across all career levels.",
    ),
    (
        "Community & Belonging",
        "We provide a global community where developers can build strong bonds in the tech space.",
    ),
]


def load_fixture(name):
    path = FIXTURES / name
    if not path.exists():
        return None
    return json.loads(path.read_text())


class Command(BaseCommand):
    help = "Create the initial Wagtail page tree, settings, and snippets."

    @transaction.atomic
    def handle(self, *args, **options):
        home = self.create_page_tree()
        self.seed_settings(home)
        self.seed_snippets()
        self.stdout.write(self.style.SUCCESS("Site bootstrapped."))

    # ── Page tree ─────────────────────────────────────────────────────────

    def create_page_tree(self):
        root = Page.objects.get(depth=1)
        site = Site.objects.filter(is_default_site=True).first()

        home = HomePage.objects.first()
        if home is None:
            # Wagtail ships a stub page at slug "home"; retire it so ours can
            # take that slot and the default Site can point at it.
            stub = Page.objects.filter(depth=2, slug="home").first()
            if stub and site and site.root_page_id == stub.pk:
                site.root_page = root
                site.save()
            if stub:
                stub.delete()

            home = HomePage(
                title="Black Python Devs",
                slug="home",
                body=[
                    (
                        "card_grid",
                        {
                            "heading": "Our Principles",
                            "cards": [
                                {"heading": h, "text": f"<p>{t}</p>", "link_url": "", "link_text": ""}
                                for h, t in PRINCIPLES
                            ],
                            "link_url": "/about/",
                            "link_text": "Learn More",
                        },
                    )
                ],
            )
            root.add_child(instance=home)
            home.save_revision().publish()
            self.stdout.write("Created home page.")

        # Point the default site at our home page and retire Wagtail's stub.
        if site:
            site.root_page = home
            site.hostname = site.hostname or "localhost"
            site.site_name = "Black Python Devs"
            site.save()
        else:
            Site.objects.create(
                hostname="localhost", port=80, root_page=home, is_default_site=True, site_name="Black Python Devs"
            )

        Page.objects.filter(slug="home", depth=2).exclude(pk=home.pk).delete()

        self.get_or_create_child(
            home,
            AboutPage,
            title="About Us",
            slug="about",
            defaults={
                "body": [("paragraph", self.about_story())],
                "community_body": self.community_body(),
            },
        )
        self.get_or_create_child(
            home,
            BlogIndexPage,
            title="News",
            slug="news",
            defaults={"introduction": "Updates from the Black Python Devs community."},
        )
        events_index = self.get_or_create_child(
            home,
            EventIndexPage,
            title="Events",
            slug="events",
            defaults={
                "meetups_body": (
                    "Join us every Friday for a cup of coffee and a chance to code with fellow Python "
                    "enthusiasts. Our community is open to all levels of experience, sharing tips and "
                    "tricks, and working on projects together."
                ),
                "grants_note": (
                    "Interested in Black Python Devs supporting your event? Review our grant criteria at "
                    "https://github.com/BlackPythonDevs/blackpythondevs/blob/main/policies/event-grants.md "
                    "and email your prospectus to sponsorships@blackpythondevs.com"
                ),
            },
        )
        self.get_or_create_child(
            home,
            SupportPage,
            title="Support",
            slug="support",
            defaults={
                "body": [
                    (
                        "paragraph",
                        "<p>Black Python Devs is a Non-Profit, fiscally hosted under the "
                        '<a href="https://foundation.gnome.org/">GNOME Foundation</a>. The GNOME Foundation '
                        "takes a small percentage for administration costs and support but at least 90% of "
                        "proceeds goes directly to the Black Python Devs Fund.</p>",
                    )
                ],
                "pitch_deck_url": "https://www.canva.com/design/DAGKXBERZ2s/AbT0GzW284THN6wSayNMMg/view?embed",
            },
        )

        self.get_or_create_child(
            home,
            MembershipPage,
            title="Become a Member",
            slug="become-a-member",
            defaults={
                "body": [
                    (
                        "card_grid",
                        {
                            "heading": "",
                            "cards": [
                                {"heading": h, "text": f"<p>{t}</p>", "link_url": "", "link_text": ""}
                                for h, t in MEMBER_BENEFITS
                            ],
                            "link_url": "",
                            "link_text": "",
                        },
                    )
                ],
                "discord_body": (
                    "<p>Our Discord is where the day-to-day community lives. Connect your "
                    "Discord account from your member area and we'll give you the member "
                    "role, which is what lets you post in the server.</p>"
                ),
            },
        )

        for title, slug in [
            ("Code of Conduct", "code-of-conduct"),
            ("Corporate Sponsorships", "corporate-sponsorships"),
            ("Student Ambassador Program", "student-ambassador-program"),
        ]:
            self.get_or_create_child(home, StandardPage, title=title, slug=slug)

        self.seed_sponsored_events(events_index)
        return home

    def get_or_create_child(self, parent, model, *, title, slug, defaults=None):
        existing = model.objects.filter(slug=slug).first()
        if existing:
            return existing
        page = model(title=title, slug=slug, **(defaults or {}))
        parent.add_child(instance=page)
        page.save_revision().publish()
        self.stdout.write(f"Created {model.__name__}: {title}")
        return page

    def seed_sponsored_events(self, events_index):
        data = load_fixture("sponsored_events.json")
        if not data:
            return

        # Sponsorship records now live in the sponsorships app as standalone rows.
        # The source JSON carries no status or payment data, so seed everything
        # in the past as completed and paid; editors correct the community
        # (non-monetary) ones by unticking `paid`, and current-year events move
        # to completed once they've happened.
        #
        # `countries` maps event name → ISO 3166-1 alpha-2 code (an event is in
        # the same country every year, so it is keyed by name, not year/region).
        # Setting `country` re-derives `region` on save(); the fixture's region
        # grouping is a fallback for any name missing from the map.
        countries = data.get("countries", {})
        if not SponsorshipRequest.objects.exists():
            this_year = datetime.date.today().year
            for year, regions in data.get("sponsored", {}).items():
                for region, names in regions.items():
                    for name in names:
                        SponsorshipRequest.objects.create(
                            year=int(year),
                            region=region,
                            country=countries.get(name, ""),
                            name=name,
                            status=(
                                SponsorshipRequest.COMPLETED
                                if int(year) < this_year
                                else SponsorshipRequest.APPROVED
                            ),
                            paid=True,
                        )

        # BPD-organised events become child pages editors can flesh out.
        for entry in data.get("bpd", []):
            title = entry["title"]
            if EventPage.objects.filter(title=title).exists():
                continue
            page = EventPage(title=title, description="")
            events_index.add_child(instance=page)
            page.save_revision().publish()

    # ── Settings ──────────────────────────────────────────────────────────

    def seed_settings(self, home):
        site = Site.objects.get(is_default_site=True)

        nav = NavigationSettings.for_site(site)
        if not nav.menu_items.exists():
            for order, (text, url, icon) in enumerate(NAV_ITEMS):
                NavigationItem.objects.create(setting=nav, sort_order=order, text=text, url=url, icon=icon)
            nav.save()

        # Defaults on the model fields do the work; this just materialises rows.
        SocialSettings.for_site(site).save()
        FooterSettings.for_site(site).save()

    # ── Snippets ──────────────────────────────────────────────────────────

    def seed_snippets(self):
        for order, (name, url, logo) in enumerate(SPONSORS):
            Sponsor.objects.update_or_create(
                name=name, defaults={"url": url, "logo_static_path": logo, "sort_order": order}
            )

        if leadership := load_fixture("leadership.json"):
            self.seed_leaders(leadership)

        for order, partner in enumerate(load_fixture("partnerships.json") or []):
            logo = (partner.get("logo") or "").lstrip("/").removeprefix("assets/")
            Partner.objects.update_or_create(
                name=partner["name"],
                defaults={
                    "url": partner.get("url", ""),
                    "promo_code": partner.get("promo_code", ""),
                    "description": partner.get("description", ""),
                    "logo_static_path": logo,
                    "sort_order": order,
                },
            )

        for year, names in (load_fixture("foundational_supporters.json") or {}).items():
            for name in names:
                FoundationalSupporter.objects.get_or_create(name=name, year=int(year))

        for author in load_fixture("authors.json") or []:
            social = author.get("social") or {}
            Author.objects.update_or_create(
                name=author["name"],
                defaults={
                    "bio": author.get("bio") or "",
                    "bpd_role": author.get("bpd_role") or "",
                    "website": social.get("website") or "",
                    "mastodon": social.get("mastodon") or "",
                    "linkedin": social.get("linkedin") or "",
                    "youtube": social.get("youtube") or "",
                },
            )

    def seed_leaders(self, data):
        groups = [
            (Leader.EXECUTOR, data.get("Executors", [])),
            (Leader.TEAM_LEAD, data.get("Leaders", [])),
            (Leader.ADVISOR, data.get("Advisors", [])),
            (Leader.COUNCIL, data.get("Council", [])),
        ]
        for role, members in groups:
            for order, member in enumerate(members):
                # Advisors and council are plain name strings; the rest are dicts.
                if isinstance(member, str):
                    member = {"name": member}
                photo = member.get("image") or ""
                if photo.startswith("/assets/"):
                    photo = photo.replace("/assets/", f"{django_settings.STATIC_URL}", 1)
                Leader.objects.update_or_create(
                    name=member["name"],
                    role=role,
                    defaults={
                        "title": member.get("title", ""),
                        "photo_url": photo,
                        "sort_order": order,
                    },
                )

    # ── Long-form copy ────────────────────────────────────────────────────

    def about_story(self):
        return (
            "<p>Black Python Devs was created by its founder Jay Miller after seeing a trend of the same "
            "handful of Black developers speaking at major conferences, taking leadership positions, and "
            "dealing with the same challenges towards burnout.</p>"
            "<p>After attending PyCon US in 2022, he noticed they were able to physically count the number "
            "of Black developers that attended in person and that they made up less than 0.01% of the total "
            "attendees.</p>"
            "<p>At PyCon US 2023 after an open space a Discord server called Black Python Devs was created "
            "where the community could continue to encourage this momentum and support one another.</p>"
        )

    def community_body(self):
        return (
            "<p>The Black Python Devs Community is a vibrant group of developers who are passionate about "
            "Python and coding. Whether you're a seasoned developer or just starting out, there's a place "
            "for you here.</p>"
            "<h3>Connect With Us</h3>"
            '<ul><li><strong>Discord:</strong> <a href="https://discord.gg/XUc3tFqCT3">Join our server</a></li>'
            '<li><strong>Twitter/X:</strong> <a href="https://x.com/blackpythondevs">Follow us</a></li>'
            '<li><strong>Instagram:</strong> <a href="https://www.instagram.com/blackpythondevs/">Follow us</a></li>'
            '<li><strong>LinkedIn:</strong> <a href="https://www.linkedin.com/company/black-python-devs">Page</a></li>'
            '<li><strong>Email:</strong> '
            '<a href="mailto:contact@blackpythondevs.com">contact@blackpythondevs.com</a></li></ul>'
        )
