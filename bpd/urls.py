from django.apps import apps
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from neapolitan.views import Role
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.contrib.sitemaps.views import sitemap
from wagtail.documents import urls as wagtaildocs_urls

from communities.views import CommunityAdminConsole, LeaveCommunityView
from core import views as core_views
from users import views as user_views

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("cms/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("accounts/", include("allauth.urls")),
    path("members/", user_views.members, name="members"),
    path("onboarding/", user_views.onboarding, name="onboarding"),
    path("profile/", user_views.profile, name="profile"),
    # Self-service account deletion (issue #143).
    path("members/delete/", user_views.delete_account, name="account-delete"),
    # Staff-generated one-time invite links (see users.models.InviteLink).
    path("invite/<str:token>/", user_views.invite_accept, name="invite-accept"),
    path("student-ambassadors/", include("ambassadors.urls")),
    # Leadership-only: nominating people for the Leadership Council.
    path("council/nominations/", include("nominations.urls")),
    # Public Executorship Election page + council-member self-service candidacy statements.
    path("elections/", include("elections.urls")),
    # Leadership-only: nominating people for the Community Service Award.
    path("leadership/service-award/", include("service_award.urls")),
    # Leadership-only: meeting minutes console (neapolitan) with a
    # per-meeting .ics calendar download.
    path("leadership/", include("meetings.urls")),
    # Staff/Executor/Sponsor/Community Partner: broadcasting member announcements.
    path("notifications/", include("notifications.urls")),
    # Public CoC report intake + the COC Report Viewing role's console.
    path("coc/", include("coc_reports.urls")),
    # Community admins: messaging BPD leadership about their community.
    path("communities/messages/", include("community_messages.urls")),
    path("communities/<int:pk>/leave/", LeaveCommunityView.as_view(), name="communities-leave"),
    # Front-end console for community admins (neapolitan). No create/delete
    # role: staff create/delete communities in the Django admin only.
    *CommunityAdminConsole.get_urls(roles={Role.LIST, Role.DETAIL, Role.UPDATE}),
    # Event sponsorships at /event-sponsorships/: the public intake form and
    # the Executor console (neapolitan), plus 301s from the old /sponsorships/.
    path("", include("event_sponsorships.urls")),
    # Front-end CRUD for corporate sponsors (neapolitan) at
    # /corporate-sponsors/, plus 301s from the old /sponsors/ paths.
    path("", include("corporate_sponsorships.urls")),
    # Generic follow-through checklists/notes portal (Executor group).
    path("checklists/", include("checklists.urls")),
    path("sitemap.xml", sitemap),
    path("robots.txt", core_views.robots_txt, name="robots"),
    path("community-map/", core_views.community_map, name="community-map"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    if apps.is_installed("debug_toolbar"):
        urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]

# Wagtail's catch-all must stay last: it matches any remaining path.
urlpatterns += [path("", include(wagtail_urls))]
