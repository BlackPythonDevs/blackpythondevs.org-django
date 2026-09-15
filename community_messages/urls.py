from django.urls import path

from . import views

app_name = "community_messages"

urlpatterns = [
    path("", views.CommunityMessageListView.as_view(), name="list"),
    path("send/", views.SendCommunityMessageView.as_view(), name="send"),
    path("<int:pk>/", views.CommunityMessageDetailView.as_view(), name="detail"),
]
