"""Blog: an index page with pagination and individual posts."""

from django import forms
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import models
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from taggit.models import TaggedItemBase
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.fields import StreamField
from wagtail.models import Page
from wagtail.search import index

from core.blocks import BodyStreamBlock
from home.models import SEOMixin


class BlogPageTag(TaggedItemBase):
    content_object = ParentalKey("blog.BlogPage", related_name="tagged_items", on_delete=models.CASCADE)


class BlogIndexPage(SEOMixin, Page):
    """Paginated list of posts — the old /blog/blogN.html archive."""

    introduction = models.TextField(blank=True)
    posts_per_page = models.PositiveSmallIntegerField(default=10)

    content_panels = Page.content_panels + [FieldPanel("introduction"), FieldPanel("posts_per_page")]

    subpage_types = ["blog.BlogPage", "blog.CustomBlogPage"]
    max_count = 1

    def get_posts(self, request):
        # BlogPage.objects includes CustomBlogPage rows too (multi-table
        # inheritance: they have a row in this table as well), so a sponsor
        # announcement lists, paginates, and tag-filters exactly like any
        # other post with no extra query.
        posts = BlogPage.objects.child_of(self).live().public().order_by("-date")
        if tag := request.GET.get("tag"):
            posts = posts.filter(tags__slug=tag)
        return posts.prefetch_related("authors")

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        paginator = Paginator(self.get_posts(request), self.posts_per_page)
        try:
            posts = paginator.page(request.GET.get("page"))
        except PageNotAnInteger:
            posts = paginator.page(1)
        except EmptyPage:
            posts = paginator.page(paginator.num_pages)
        context["posts"] = posts
        context["paginator"] = paginator
        context["active_tag"] = request.GET.get("tag", "")
        return context


class BlogPage(SEOMixin, Page):
    """A single news post."""

    date = models.DateField("post date")
    description = models.TextField(blank=True, help_text="Shown in listings and as the meta description.")
    featured_image = models.ForeignKey(
        "core.CustomImage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "Shown uncropped, letterboxed in a 3:2 frame in listings. Use a 3:2 image "
            "(e.g. 1200x800) to fill the frame. Transparent PNGs appear on a light "
            "background, so avoid white artwork."
        ),
    )
    authors = ParentalManyToManyField("core.Author", blank=True, related_name="posts")
    body = StreamField(BodyStreamBlock(), blank=True, use_json_field=True)
    tags = ClusterTaggableManager(through=BlogPageTag, blank=True)

    content_panels = Page.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("date"),
                FieldPanel("authors", widget=forms.CheckboxSelectMultiple),
                FieldPanel("tags"),
            ],
            heading="Post metadata",
        ),
        FieldPanel("description"),
        FieldPanel("featured_image"),
        FieldPanel("body"),
    ]

    search_fields = Page.search_fields + [
        index.SearchField("description"),
        index.SearchField("body"),
        index.FilterField("date"),
    ]

    parent_page_types = ["blog.BlogIndexPage"]

    @property
    def author_names(self):
        return [author.name for author in self.authors.all()]


class CustomBlogPage(BlogPage):
    """A BlogPage tied to a corporate sponsor — a welcome or renewal announcement.

    Lives in the same tree as ordinary posts (a subpage of BlogIndexPage,
    listed by BlogIndexPage.get_posts() like any other BlogPage) so no
    separate listing view or template is needed; `template` below just
    points back at BlogPage's own, since Wagtail's default lookup would
    otherwise look for a "custom_blog_page.html" that doesn't exist.
    """

    sponsor = models.ForeignKey(
        "core.Sponsor",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="announcement_posts",
    )

    content_panels = BlogPage.content_panels + [FieldPanel("sponsor")]

    parent_page_types = ["blog.BlogIndexPage"]
    template = "blog/blog_page.html"
