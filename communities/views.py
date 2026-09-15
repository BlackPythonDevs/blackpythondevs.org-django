"""Front-end console for community admins.

Two separate surfaces, mirroring the split already used elsewhere:

- `CommunityAdminConsole` — a neapolitan CRUDView, list/detail/update only
  (see `sponsorships.views.SponsorshipRequestView` for the pattern it copies).
  No create or delete role is wired up at all: staff create communities in
  the Django admin, and a community admin can never delete a `Community`
  outright — only leave it (`LeaveCommunityView`).
- `SendCommunityMessageView` / `CommunityMessageListView` — a plain
  compose-and-send flow, mirroring
  `notifications.views.SendNotificationView` / `NotificationListView`.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView
from neapolitan.views import CRUDView

from .forms import CommunityAdminForm, CommunityMessageForm
from .models import Community, CommunityAdmin, CommunityMessage, can_manage_community


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


class CommunityMessageSenderRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return can_manage_community(self.request.user)

    def handle_no_permission(self):
        self.raise_exception = self.request.user.is_authenticated
        return super().handle_no_permission()


class CommunityMessageListView(CommunityMessageSenderRequiredMixin, ListView):
    """Messages sent by communities the requester admins, newest first."""

    model = CommunityMessage
    template_name = "communities/message_list.html"
    context_object_name = "community_messages"
    paginate_by = 25

    def get_queryset(self):
        return (
            CommunityMessage.objects.filter(community__admins=self.request.user)
            .select_related("community", "sender")
            .distinct()
        )


class SendCommunityMessageView(CommunityMessageSenderRequiredMixin, CreateView):
    """The compose form. Sending happens as soon as it validates."""

    model = CommunityMessage
    form_class = CommunityMessageForm
    template_name = "communities/message_form.html"
    success_url = reverse_lazy("communities:message-list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["sender"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.sender = self.request.user
        response = super().form_valid(form)
        count = self.object.send()
        if count:
            messages.success(self.request, f"Sent to {count} leadership member{'' if count == 1 else 's'}.")
        else:
            messages.warning(self.request, "No leadership members matched that region — nothing was sent.")
        return response
