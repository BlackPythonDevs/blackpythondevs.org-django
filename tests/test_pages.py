import datetime

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from blog.models import BlogIndexPage, BlogPage
from core.models import Author, FoundationalSupport, Leader, Sponsor
from core.supporters import SUPPORTER_EMAIL_DOMAIN, get_or_create_supporter_user
from events.models import EventIndexPage
from home.models import AboutPage, StandardPage, SupportPage

pytestmark = pytest.mark.django_db


def test_bootstrap_creates_page_tree(bootstrapped_site):
    assert bootstrapped_site.slug == "home"
    assert AboutPage.objects.count() == 1
    assert BlogIndexPage.objects.count() == 1
    assert EventIndexPage.objects.count() == 1
    assert SupportPage.objects.count() == 1
    assert StandardPage.objects.filter(slug="code-of-conduct").exists()


def test_bootstrap_is_idempotent(bootstrapped_site):
    from wagtail.models import Page

    before = Page.objects.count()
    call_command("bootstrap_site", verbosity=0)
    assert Page.objects.count() == before


def test_bootstrap_seeds_snippets(bootstrapped_site):
    assert Sponsor.objects.filter(active=True).exists()
    assert Leader.objects.filter(role=Leader.EXECUTOR).exists()
    assert Leader.objects.filter(role=Leader.COUNCIL).exists()
    assert Author.objects.exists()


def test_principles_heading_is_not_double_escaped(bootstrapped_site):
    """The seed copy must hold a literal '&', not a pre-escaped entity."""
    headings = [
        card["heading"]
        for block in bootstrapped_site.body
        if block.block_type == "card_grid"
        for card in block.value["cards"]
    ]
    assert "Community & Belonging" in headings
    assert not any("&amp;" in h for h in headings)


@pytest.mark.parametrize(
    "path",
    ["/", "/about/", "/news/", "/events/", "/support/", "/code-of-conduct/"],
)
def test_pages_render(client, bootstrapped_site, path):
    assert client.get(path).status_code == 200


def test_home_page_renders_ampersand_correctly(client, bootstrapped_site):
    html = client.get("/").content.decode()
    assert "Community &amp; Belonging" in html
    assert "&amp;amp;" not in html


def test_code_of_conduct_page_links_to_the_report_form_top_and_bottom(client, bootstrapped_site):
    html = client.get("/code-of-conduct/").content.decode()
    # One link from the site footer, plus one above and one below the body.
    assert html.count('href="/coc/report/"') == 3


def test_other_standard_pages_only_have_the_footer_report_link(client, bootstrapped_site):
    html = client.get("/corporate-sponsorships/").content.decode()
    assert html.count('href="/coc/report/"') == 1


class TestBlog:
    @pytest.fixture
    def post(self, bootstrapped_site):
        index = BlogIndexPage.objects.get()
        author = Author.objects.create(name="Test Author", bio="A bio.")
        page = BlogPage(
            title="Hello World",
            slug="hello-world",
            date=datetime.date(2026, 1, 1),
            description="A test post.",
            body=[("paragraph", "<p>Body copy.</p>")],
        )
        index.add_child(instance=page)
        page.save_revision().publish()
        page.authors.add(author)
        page.save()
        return page

    def test_post_renders(self, client, post):
        response = client.get(post.url)
        assert response.status_code == 200
        html = response.content.decode()
        assert "Hello World" in html
        assert "Test Author" in html
        assert "A bio." in html

    def test_post_appears_in_index(self, client, post):
        html = client.get("/news/").content.decode()
        assert "Hello World" in html

    def test_index_pagination_does_not_break_on_bad_page(self, client, post):
        assert client.get("/news/?page=not-a-number").status_code == 200
        assert client.get("/news/?page=9999").status_code == 200

    def test_tag_filter(self, client, post):
        post.tags.add("community")
        post.save_revision().publish()
        assert "Hello World" in client.get("/news/?tag=community").content.decode()
        assert "Hello World" not in client.get("/news/?tag=missing").content.decode()


class TestFoundationalSupport:
    """Supporters are user accounts; the page lists only public support."""

    def test_bootstrap_creates_unverified_supporter_accounts(self, bootstrapped_site):
        support = FoundationalSupport.objects.select_related("user").first()
        assert support is not None
        user = support.user
        assert user.display_name
        assert user.email.endswith(f"@{SUPPORTER_EMAIL_DOMAIN}")
        assert not user.has_usable_password()

    def test_repeat_support_reuses_one_account(self, bootstrapped_site):
        User = get_user_model()
        years = {2024, 2025}
        user, created = get_or_create_supporter_user(User, "Grace Hopper")
        assert created
        for year in years:
            FoundationalSupport.objects.create(user=user, year=year)

        again, created = get_or_create_supporter_user(User, "Grace Hopper")
        assert not created and again.pk == user.pk
        assert set(user.foundational_support.values_list("year", flat=True)) == years

    def test_only_listed_support_is_published(self, client, bootstrapped_site):
        User = get_user_model()
        public, _ = get_or_create_supporter_user(User, "Listed Person")
        private, _ = get_or_create_supporter_user(User, "Private Person")
        FoundationalSupport.objects.create(user=public, year=2026)
        FoundationalSupport.objects.create(user=private, year=2026, status=FoundationalSupport.ANONYMOUS)

        html = client.get("/support/").content.decode()
        assert "Listed Person" in html
        assert "Private Person" not in html


class TestPartnerPromoCodes:
    """Partnerships are public, but the promo code is a member perk."""

    def test_anonymous_visitors_do_not_see_promo_codes(self, client, bootstrapped_site):
        html = client.get("/support/").content.decode()
        assert "bpd-20pc-1c1da" not in html
        assert "BLACKPYTHONDEVS" not in html
        assert "Log in" in html

    def test_logged_in_members_see_promo_codes(self, client, bootstrapped_site):
        User = get_user_model()
        user = User.objects.create_user(username="member", email="member@example.com", password="password123")
        client.force_login(user)

        html = client.get("/support/").content.decode()
        assert "bpd-20pc-1c1da" in html
        assert "BLACKPYTHONDEVS" in html


class TestDonateBlock:
    def test_block_embeds_commitchange_with_designation(self, client, bootstrapped_site):
        from home.models import StandardPage

        page = StandardPage.objects.get(slug="student-ambassador-program")
        page.body = [("donate", {"heading": "Give", "designation": "Leadership Summit", "amounts": "10,20"})]
        page.save_revision().publish()

        html = client.get(page.url).content.decode()
        assert 'class="commitchange-donate"' in html
        assert 'data-designation="Leadership Summit"' in html
        assert 'data-custom-amounts="10,20"' in html

    def test_monthly_giving_can_be_disabled(self, client, bootstrapped_site):
        from home.models import StandardPage

        page = StandardPage.objects.get(slug="student-ambassador-program")
        page.body = [("donate", {"disable_monthly": True})]
        page.save_revision().publish()
        assert 'data-type="one-time"' in client.get(page.url).content.decode()

        page.body = [("donate", {"disable_monthly": False})]
        page.save_revision().publish()
        assert "data-type" not in client.get(page.url).content.decode()


class TestSponsorStrip:
    """Issue #170: sponsor logos must keep their aspect ratio, never stretch."""

    @pytest.fixture
    def wide_logo_image(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        from core.models import CustomImage

        buf = io.BytesIO()
        Image.new("RGB", (200, 20), "cyan").save(buf, format="PNG")  # deliberately wide
        return CustomImage.objects.create(
            title="Temporal logo",
            file=SimpleUploadedFile("temporal.png", buf.getvalue(), content_type="image/png"),
        )

    def test_uploaded_logo_renders_without_a_fixed_inline_height(self, client, site, wide_logo_image):
        from core.models import Sponsor

        Sponsor.objects.create(name="Temporal", url="https://temporal.io", logo=wide_logo_image)
        html = client.get("/").content.decode()
        assert "Temporal logo" in html  # the strip renders the sponsor
        # A fixed inline height with max-width clamping is what stretched logos.
        assert 'style="height' not in html

    def test_static_path_logo_renders_without_a_fixed_inline_height(self, client, site):
        from core.models import Sponsor

        Sponsor.objects.create(name="JetBrains", url="https://jetbrains.com", logo_static_path="images/jetbrains.webp")
        html = client.get("/").content.decode()
        assert "JetBrains logo" in html
        assert 'style="height' not in html

    def test_css_sizes_logos_proportionally(self, site):
        """The shared .sponsor img rule must fix the height, keep width auto,
        and letterbox via object-fit so ratios survive narrow grid cells."""
        from django.conf import settings

        css = (settings.BASE_DIR / "static" / "css" / "bpd.css").read_text()
        rule = css.split(".sponsor img {", 1)[1].split("}", 1)[0]
        assert "height: 2rem" in rule
        assert "width: auto" in rule
        assert "object-fit: contain" in rule
