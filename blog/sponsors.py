"""Draft a sponsor announcement post whenever invoice_paid_date is (re)set.

Called from `core.Sponsor.save()`, which imports this module lazily — kept
here rather than in `core` because it needs `CustomBlogPage`, and `core`
shouldn't import `blog` at module load time (blog already imports
`core.blocks`, so that would be circular).
"""

from django.utils.text import slugify

from .models import BlogIndexPage, CustomBlogPage


def draft_sponsor_announcement(sponsor):
    """Create a draft CustomBlogPage for `sponsor`, unless one already exists
    for this exact invoice_paid_date (guards against duplicate drafts from a
    double save), or there's nowhere to put it.
    """
    if CustomBlogPage.objects.filter(sponsor=sponsor, date=sponsor.invoice_paid_date).exists():
        return

    blog_index = BlogIndexPage.objects.first()
    if blog_index is None:
        return

    is_renewal = CustomBlogPage.objects.filter(sponsor=sponsor).exists()
    if is_renewal:
        title = f"{sponsor.name} renews their sponsorship"
        description = f"{sponsor.name} has renewed their sponsorship of Black Python Devs."
    else:
        title = f"Welcome our new sponsor: {sponsor.name}"
        description = f"Please join us in welcoming {sponsor.name} as a sponsor of Black Python Devs."

    page = CustomBlogPage(
        title=title,
        slug=f"{slugify(sponsor.name)}-sponsorship-{sponsor.invoice_paid_date.isoformat()}",
        date=sponsor.invoice_paid_date,
        description=description,
        sponsor=sponsor,
        featured_image=sponsor.logo,
        body=[("paragraph", f"<p>{description}</p>")],
        live=False,
    )
    blog_index.add_child(instance=page)
    page.save_revision()
