from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.clickjacking import xframe_options_sameorigin


@cache_control(max_age=60 * 60 * 24)
@xframe_options_sameorigin
def community_map(request):
    return render(request, "core/map.html", {"carto_api_key": settings.CARTO_API_KEY})


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
