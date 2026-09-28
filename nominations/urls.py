from django.urls import path

from . import views

app_name = "nominations"

urlpatterns = [
    path("", views.NominationListView.as_view(), name="list"),
    path("new/", views.NominateView.as_view(), name="nominate"),
    path("<int:pk>/", views.NominationDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.NominationUpdateView.as_view(), name="edit"),
    path("<int:pk>/withdraw/", views.NominationWithdrawView.as_view(), name="withdraw"),
    path("<int:pk>/second/", views.NominationSecondView.as_view(), name="second"),
    path("<int:pk>/object/", views.NominationObjectView.as_view(), name="object"),
    path("<int:pk>/confirm/", views.NominationSendConfirmationView.as_view(), name="confirm"),
]
