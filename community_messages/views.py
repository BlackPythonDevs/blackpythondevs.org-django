"""Compose-and-send front end for messages to BPD leadership.

Mirrors notifications.views' compose/list split, but for the opposite
direction (community admin -> leadership rather than staff -> members).
"""

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView

from communities.models import can_manage_community
from core.models import CustomImage

from .forms import CommunityMessageForm
from .models import CommunityMessage, is_leadership, messages_for_leader


class CommunityMessageSenderRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return can_manage_community(self.request.user)

    def handle_no_permission(self):
        self.raise_exception = self.request.user.is_authenticated
        return super().handle_no_permission()


class CommunityMessageViewerRequiredMixin(UserPassesTestMixin):
    """Either side of a message can read it: the sending community's admins,
    or a Leadership member it actually reached."""

    def test_func(self):
        user = self.request.user
        return can_manage_community(user) or is_leadership(user) or user.is_superuser

    def handle_no_permission(self):
        self.raise_exception = self.request.user.is_authenticated
        return super().handle_no_permission()


class LeadershipInboxRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return is_leadership(user) or user.is_superuser

    def handle_no_permission(self):
        self.raise_exception = self.request.user.is_authenticated
        return super().handle_no_permission()


class CommunityMessageListView(CommunityMessageSenderRequiredMixin, ListView):
    """Messages sent by communities the requester admins, newest first."""

    model = CommunityMessage
    template_name = "community_messages/message_list.html"
    context_object_name = "community_messages"
    paginate_by = 25

    def get_queryset(self):
        return (
            CommunityMessage.objects.filter(community__admins=self.request.user)
            .select_related("community", "sender")
            .distinct()
        )


class CommunityMessageDetailView(CommunityMessageViewerRequiredMixin, DetailView):
    """A single past message — visible to the sending community's admins and
    to any Leadership member it actually reached."""

    model = CommunityMessage
    template_name = "community_messages/message_detail.html"
    context_object_name = "community_message"

    def get_queryset(self):
        user = self.request.user
        qs = CommunityMessage.objects.filter(community__admins=user)
        if is_leadership(user) or user.is_superuser:
            qs = qs | messages_for_leader(user)
        return qs.distinct().select_related("community", "sender")


class LeadershipInboxView(LeadershipInboxRequiredMixin, ListView):
    """Every sent message that reached this Leadership member, newest first."""

    model = CommunityMessage
    template_name = "community_messages/message_inbox.html"
    context_object_name = "community_messages"
    paginate_by = 25

    def get_queryset(self):
        return messages_for_leader(self.request.user).select_related("community", "sender")


class SendCommunityMessageView(CommunityMessageSenderRequiredMixin, CreateView):
    """The compose form. Sending happens as soon as it validates."""

    model = CommunityMessage
    form_class = CommunityMessageForm
    template_name = "community_messages/message_form.html"
    success_url = reverse_lazy("community_messages:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["sender"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.sender = self.request.user

        image_file = form.cleaned_data.get("image")
        if image_file:
            image = CustomImage.objects.create(title=image_file.name, file=image_file)
            image_url = self.request.build_absolute_uri(image.get_rendition("width-800").url)
            form.instance.body = f"{form.instance.body}\n\n![]({image_url})\n"

        response = super().form_valid(form)
        count = self.object.send()
        if count:
            messages.success(self.request, f"Sent to {count} leadership member{'' if count == 1 else 's'}.")
        else:
            messages.warning(self.request, "No leadership members matched that region — nothing was sent.")
        return response
