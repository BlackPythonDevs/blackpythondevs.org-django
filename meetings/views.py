"""Front-end console for leadership meeting minutes.

Neapolitan CRUD, same shape as core.views.SponsorView: requiring the full
add/change/delete/view set keeps this a management console for users who can
do everything with it (in practice the Leadership Council, Executor group,
and superusers) — see core.views.SponsorView for the same reasoning. The
detail page links the .ics download (MeetingICSView) so the calendar invite
travels with the record.
"""

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.generic import View
from neapolitan.views import CRUDView

from .forms import MeetingForm
from .models import CalendarFeed, Meeting


class MeetingView(PermissionRequiredMixin, CRUDView):
    model = Meeting
    form_class = MeetingForm
    url_base = "meetings"
    fields = [
        "title",
        "scheduled_at",
        "location",
        "url",
        "notes",
    ]
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # The token-gated feed URL shown on the list page for subscribing.
        context["feed_token"] = CalendarFeed.current_token()
        return context

    # Requiring the full set keeps this a management console: only users who
    # can do everything (Leadership Council, the Executor group, and
    # superusers) get in at all.
    permission_required = [
        "meetings.view_meeting",
        "meetings.add_meeting",
        "meetings.change_meeting",
        "meetings.delete_meeting",
    ]


class MeetingICSView(PermissionRequiredMixin, View):
    """Download one upcoming meeting as an .ics calendar entry.

    Past meetings 404: an invite for a meeting that already happened is of
    no use, and the published minutes stay here — whoever still needs the
    details can subscribe to the calendar feed (MeetingCalendarFeedView).
    """

    permission_required = "meetings.view_meeting"

    def get(self, request, pk):
        meeting = get_object_or_404(Meeting, pk=pk)
        if not meeting.is_upcoming():
            raise Http404("Meeting already happened")
        response = HttpResponse(meeting.as_ics(), content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="meeting-{meeting.pk}.ics"'
        return response


class MeetingCalendarFeedView(View):
    """Subscribable .ics feed of upcoming meetings, gated by a secret token.

    Calendar clients can't hold a Django session, so the feed is public but
    requires the token CalendarFeed generated on first use (see the model):
    wrong or missing token, 404. Only upcoming meetings are included, so a
    past meeting disappears from subscribers' calendars too.
    """

    def get(self, request):
        token = request.GET.get("token", "")
        if not token or not constant_time_compare(token, CalendarFeed.current_token()):
            raise Http404("No such calendar feed")
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Black Python Devs//Meeting Minutes//EN",
            "CALSCALE:GREGORIAN",
        ]
        upcoming = Meeting.objects.filter(scheduled_at__gt=timezone.now()).order_by("scheduled_at")
        for meeting in upcoming:
            lines += meeting.as_vevent()
        lines.append("END:VCALENDAR")
        return HttpResponse("\r\n".join(lines) + "\r\n", content_type="text/calendar; charset=utf-8")
