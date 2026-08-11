"""Import markdown content from the static blackpythondevs.github.io repo.

Reads `_posts/`, `events/`, and `pages/` from the source tree and creates the
matching Wagtail pages, pulling referenced images out of `assets/images/` into
the Wagtail image library.

    python manage.py import_content --source ../blackpythondevs.github.io

Idempotent: existing pages are matched by slug and updated in place.
"""

import re
from pathlib import Path

import frontmatter
import markdown as md
from django.core.files.images import ImageFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from blog.models import BlogIndexPage, BlogPage
from core.models import Author, CustomImage
from events.models import EventIndexPage, EventPage
from home.models import HomePage, StandardPage

MARKDOWN_EXTENSIONS = ["footnotes", "fenced_code", "tables", "toc", "attr_list"]

# Jekyll post filenames are YYYY-MM-DD-the-slug.md
POST_FILENAME_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})-(?P<slug>.+)$")

# Rewrite /assets/... references to /static/... so copied assets still resolve.
ASSET_PATH_RE = re.compile(r"(?P<attr>src|href)=([\"'])/assets/(?P<rest>[^\"']+)\2")
MD_ASSET_RE = re.compile(r"\((/assets/([^)]+))\)")


class Command(BaseCommand):
    help = "Import markdown posts, events, and pages from the static site repo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default="../blackpythondevs.github.io",
            help="Path to the static site repository.",
        )
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Do not upload featured images into the Wagtail image library.",
        )
        parser.add_argument("--limit", type=int, default=0, help="Import at most N posts (for testing).")

    @transaction.atomic
    def handle(self, *args, **options):
        self.source = Path(options["source"]).expanduser().resolve()
        if not self.source.is_dir():
            raise CommandError(f"Source directory not found: {self.source}")

        self.skip_images = options["skip_images"]
        self.image_cache = {}

        home = HomePage.objects.first()
        if home is None:
            raise CommandError("No home page found. Run `manage.py bootstrap_site` first.")

        self.import_posts(options["limit"])
        self.import_events()
        self.import_pages(home)
        self.stdout.write(self.style.SUCCESS("Content import complete."))

    # ── Blog posts ────────────────────────────────────────────────────────

    def import_posts(self, limit=0):
        index = BlogIndexPage.objects.first()
        if index is None:
            self.stdout.write(self.style.WARNING("No BlogIndexPage; skipping posts."))
            return

        paths = sorted((self.source / "_posts").glob("*.md"))
        if limit:
            paths = paths[-limit:]

        for path in paths:
            post = frontmatter.load(path)
            match = POST_FILENAME_RE.match(path.stem)
            if not match:
                self.stdout.write(self.style.WARNING(f"Skipping unparseable filename: {path.name}"))
                continue

            slug = slugify(post.get("slug") or match.group("slug"))
            date = post.get("date") or match.group("date")
            title = post.get("title") or slug.replace("-", " ").title()

            page = BlogPage.objects.filter(slug=slug).first()
            created = page is None
            if created:
                page = BlogPage(slug=slug)

            page.title = title
            page.date = str(date)[:10]
            page.description = (post.get("description") or "").strip()
            page.body = [("html", self.render_body(post.content))]

            if featured := post.get("featured_image"):
                page.featured_image = self.get_image(featured)

            if created:
                index.add_child(instance=page)
            page.save()
            page.authors.set(self.get_authors(post.get("author")))
            page.save()
            page.save_revision().publish()

            self.stdout.write(f"{'Created' if created else 'Updated'} post: {title}")

    def get_authors(self, names):
        if not names:
            return []
        if isinstance(names, str):
            names = [names]
        authors = []
        for name in names:
            author, _ = Author.objects.get_or_create(name=name.strip())
            authors.append(author)
        return authors

    # ── Events ────────────────────────────────────────────────────────────

    def import_events(self):
        index = EventIndexPage.objects.first()
        if index is None:
            self.stdout.write(self.style.WARNING("No EventIndexPage; skipping events."))
            return

        for path in sorted((self.source / "events").glob("*.md")):
            event = frontmatter.load(path)
            slug = slugify(event.get("slug") or path.stem)
            title = event.get("title") or slug.replace("-", " ").title()

            page = EventPage.objects.filter(slug=slug).first()
            # bootstrap_site may have created a placeholder under a Wagtail-derived
            # slug; fall back to matching on title before creating a duplicate.
            if page is None:
                page = EventPage.objects.filter(title=title).first()
            created = page is None
            if created:
                page = EventPage(slug=slug)

            page.title = title
            page.slug = slug
            page.body = [("html", self.render_body(event.content))]
            prospectus = (event.get("prospectus") or "").rstrip("[]")
            page.prospectus_url = prospectus if prospectus.startswith("http") else ""

            if banner := event.get("event_banner"):
                page.banner = self.get_image(banner)

            if created:
                index.add_child(instance=page)
            page.save()
            page.save_revision().publish()
            self.stdout.write(f"{'Created' if created else 'Updated'} event: {title}")

    # ── Standalone pages ──────────────────────────────────────────────────

    def import_pages(self, home):
        # The static repo's filenames don't match the site's URLs, so map them.
        slug_overrides = {
            "coc": "code-of-conduct",
            "corporate-sponsors": "corporate-sponsorships",
            "student-ambassadors": "student-ambassador-program",
        }

        for path in sorted((self.source / "pages").glob("*.md")):
            doc = frontmatter.load(path)
            slug = slug_overrides.get(path.stem, slugify(path.stem))
            title = doc.get("title") or slug.replace("-", " ").title()

            page = StandardPage.objects.filter(slug=slug).first()
            created = page is None
            if created:
                page = StandardPage(slug=slug)

            page.title = title
            page.introduction = (doc.get("description") or "").strip()
            page.body = [("html", self.render_body(doc.content))]

            if created:
                home.add_child(instance=page)
            page.save()
            page.save_revision().publish()
            self.stdout.write(f"{'Created' if created else 'Updated'} page: {title}")

    # ── Helpers ───────────────────────────────────────────────────────────

    def render_body(self, content):
        """Markdown → HTML, with /assets/ paths rewritten to /static/."""
        html = md.markdown(content, extensions=MARKDOWN_EXTENSIONS)
        html = MD_ASSET_RE.sub(lambda m: f"(/static/{m.group(2)})", html)
        html = ASSET_PATH_RE.sub(lambda m: f'{m.group("attr")}="/static/{m.group("rest")}"', html)
        return html

    def get_image(self, path):
        """Upload an asset-relative image into the Wagtail image library once."""
        if self.skip_images or not path:
            return None
        if path in self.image_cache:
            return self.image_cache[path]

        relative = path.lstrip("/").removeprefix("assets/")
        source_file = self.source / "assets" / relative
        if not source_file.exists():
            self.stdout.write(self.style.WARNING(f"Image not found: {path}"))
            self.image_cache[path] = None
            return None

        title = source_file.stem.replace("_", " ").replace("-", " ")
        existing = CustomImage.objects.filter(title=title).first()
        if existing:
            self.image_cache[path] = existing
            return existing

        with source_file.open("rb") as fh:
            image = CustomImage(title=title, file=ImageFile(fh, name=source_file.name))
            image.save()

        self.image_cache[path] = image
        return image
