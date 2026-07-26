import datetime


def site_context(request):
    """Values every template needs, matching the old site's global site_vars.

    `page` defaults to None so base.html can reference it safely from views
    Wagtail doesn't serve (allauth, error pages). Wagtail's own page views put
    the real page into the context, which takes precedence over this default.
    """
    return {
        "page": None,
        "current_year": datetime.date.today().year,
        "SITE_TITLE": "Black Python Devs",
    }
