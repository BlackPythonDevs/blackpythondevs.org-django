"""Front-end console for community admins.

- `CommunityAdminConsole` — a neapolitan CRUDView, list/detail/update only
  (see `sponsorships.views.SponsorshipRequestView` for the pattern it copies).
  No create or delete role is wired up at all: staff create communities in
  the Django admin, and a community admin can never delete a `Community`
  outright — only leave it (`LeaveCommunityView`).

Messaging leadership lives in the separate `community_messages` app.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from neapolitan.views import CRUDView

from .forms import CommunityAdminForm
from .models import Community, CommunityAdmin


class CommunityAdminConsole(PermissionRequiredMixin, CRUDView):
    model = Community
    url_base = "communities"
    form_class = CommunityAdminForm
    filterset_fields = ["is_online", "region"]
    paginate_by = 25

    # Only view_community + change_community are granted to the "Community
    # Admins" group (see the group-provisioning migration) — no add/delete,
    # so this list is also what keeps create/update reachable while any
    # accidental create/delete URL would 403 rather than silently work.
    permission_required = ["communities.view_community", "communities.change_community"]

    def get_queryset(self):
        return Community.objects.filter(admins=self.request.user)


class LeaveCommunityView(LoginRequiredMixin, View):
    """Self-service "leave this community": deletes the requester's own
    `CommunityAdmin` row and nothing else — never the `Community` itself."""

    def get_object(self):
        return get_object_or_404(CommunityAdmin, community_id=self.kwargs["pk"], user=self.request.user)

    def get(self, request, *args, **kwargs):
        return render(request, "communities/community_leave_confirm.html", {"admin_link": self.get_object()})

    def post(self, request, *args, **kwargs):
        admin_link = self.get_object()
        community_name = admin_link.community.name
        admin_link.delete()
        messages.success(request, f"You're no longer an admin of {community_name}.")
        return redirect("communities-list")
