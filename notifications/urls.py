from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "notifications"

# /notifications/ is the signed-in member's own inbox (issue #133): it used to
# be the sender-facing list of every broadcast, which showed something entirely
# different from /notifications/inbox/ and offered no way to open a message.
# The broadcast archive lives at sent/ now, and the old inbox URL redirects.
urlpatterns = [
    path("", views.NotificationInboxView.as_view(), name="inbox"),
    path("inbox/", RedirectView.as_view(pattern_name="notifications:inbox"), name="old_inbox"),
    path("new/", views.SendNotificationView.as_view(), name="send"),
    path("sent/", views.NotificationListView.as_view(), name="sent"),
    path("<int:pk>/", views.NotificationDetailView.as_view(), name="detail"),
]
