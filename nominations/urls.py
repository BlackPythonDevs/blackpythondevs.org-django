from django.urls import path

from . import views

app_name = "nominations"

urlpatterns = [
    path("", views.NominationListView.as_view(), name="list"),
    path("new/", views.NominateView.as_view(), name="nominate"),
    path("<int:pk>/", views.NominationDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.NominationUpdateView.as_view(), name="edit"),
    path("<int:pk>/withdraw/", views.NominationWithdrawView.as_view(), name="withdraw"),
]
