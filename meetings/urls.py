from django.urls import path

from .views import MeetingICSView, MeetingView

# Included under "leadership/" from bpd/urls.py, so the console lives at
# /leadership/meetings/. No app_name: neapolitan names its URLs
# "meetings-list" etc. after url_base, flat like the sponsors console.
urlpatterns = [
    path("meetings/<int:pk>/meeting.ics", MeetingICSView.as_view(), name="meetings-ics"),
    *MeetingView.get_urls(),
]
