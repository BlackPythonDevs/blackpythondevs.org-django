"""Compose-and-send front end for broadcast notifications, and each member's
own in-app notification inbox (see models.py's UserNotification, issue #98).

Staff, Executors, Sponsors, and Community Partners get in to the compose/send
views; a signed-in member outside those groups gets a 403 rather than a login
loop, and anonymous visitors are sent to log in first (see nominations.views
for the same pattern, which this mirrors). The inbox itself is just
login-required — it only ever shows a member their own notifications.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView

from core.models import CustomImage
from users.regions import PARENT_REGIONS, SUBREGION_COUNTRIES

from .forms import NotificationForm
from .models import Notification, UserNotification, can_send_notifications


class NotificationSenderRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return can_send_notifications(self.request.user)

    def handle_no_permission(self):
        self.raise_exception = self.request.user.is_authenticated
        return super().handle_no_permission()


class NotificationListView(NotificationSenderRequiredMixin, ListView):
    """Everything sent so far, newest first."""

    model = Notification
    template_name = "notifications/notification_list.html"
    context_object_name = "notifications"
    paginate_by = 25

    def get_queryset(self):
        return Notification.objects.select_related("sender").prefetch_related("roles")


class SendNotificationView(NotificationSenderRequiredMixin, CreateView):
    """The compose form. Sending happens as soon as it validates."""

    model = Notification
    form_class = NotificationForm
    template_name = "notifications/notification_form.html"
    success_url = reverse_lazy("notifications:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["sender"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Drives the clickable region map: which countries light up together
        # when one of them is clicked. Harmless to include when the sender's
        # form has no `regions` field — the template just won't render the map.
        context["region_countries"] = SUBREGION_COUNTRIES
        context["parent_regions"] = PARENT_REGIONS
        return context

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
            messages.success(self.request, f"Sent to {count} member{'' if count == 1 else 's'}.")
        else:
            messages.warning(self.request, "No members matched those filters — nothing was sent.")
        return response


class NotificationInboxView(LoginRequiredMixin, ListView):
    """The signed-in member's own in-app notifications, newest first."""

    model = UserNotification
    template_name = "notifications/notification_inbox.html"
    context_object_name = "user_notifications"
    paginate_by = 25

    def get_queryset(self):
        return UserNotification.objects.filter(recipient=self.request.user).select_related("actor")

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        if action == "mark_read":
            notification = UserNotification.objects.filter(
                pk=request.POST.get("notification_id"), recipient=request.user
            ).first()
            if notification is not None:
                notification.mark_read()
        elif action == "mark_all_read":
            self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return redirect("notifications:inbox")
