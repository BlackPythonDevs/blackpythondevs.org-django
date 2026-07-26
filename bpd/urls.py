from django.apps import apps
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.contrib.sitemaps.views import sitemap
from wagtail.documents import urls as wagtaildocs_urls

from core import views as core_views
from sponsorships.views import SponsorshipRequestView
from users import views as user_views

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("cms/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("accounts/", include("allauth.urls")),
    path("members/", user_views.members, name="members"),
    # Front-end CRUD for the Executor group (neapolitan).
    *SponsorshipRequestView.get_urls(),
    path("sitemap.xml", sitemap),
    path("robots.txt", core_views.robots_txt, name="robots"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    if apps.is_installed("debug_toolbar"):
        urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]

# Wagtail's catch-all must stay last: it matches any remaining path.
urlpatterns += [path("", include(wagtail_urls))]
