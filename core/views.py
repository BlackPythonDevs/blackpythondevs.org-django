from django.http import HttpResponse
from django.views.decorators.cache import cache_control


@cache_control(max_age=60 * 60 * 24)
def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /cms/",
        "Disallow: /django-admin/",
        "Disallow: /accounts/",
        "",
        f"Sitemap: {request.scheme}://{request.get_host()}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")
