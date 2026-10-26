"""Front-end console for leadership meeting minutes.

Neapolitan CRUD, same shape as core.views.SponsorView: requiring the full
add/change/delete/view set keeps this a management console for users who can
do everything with it (in practice the Leadership Council, Executor group,
and superusers) — see core.views.SponsorView for the same reasoning. The
detail page links the .ics download (MeetingICSView) so the calendar invite
travels with the record.
"""

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.generic import View
from neapolitan.views import CRUDView

from .models import Meeting


class MeetingView(PermissionRequiredMixin, CRUDView):
    model = Meeting
    url_base = "meetings"
    fields = [
        "title",
        "scheduled_at",
        "location",
        "url",
        "notes",
    ]
    paginate_by = 25

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
    """Download one meeting as an .ics calendar entry."""

    permission_required = "meetings.view_meeting"

    def get(self, request, pk):
        meeting = get_object_or_404(Meeting, pk=pk)
        response = HttpResponse(meeting.as_ics(), content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="meeting-{meeting.pk}.ics"'
        return response
