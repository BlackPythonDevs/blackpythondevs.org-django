from django.urls import path

from . import views

app_name = "communities"

urlpatterns = [
    path("", views.CommunityMessageListView.as_view(), name="message-list"),
    path("send/", views.SendCommunityMessageView.as_view(), name="message-send"),
]
