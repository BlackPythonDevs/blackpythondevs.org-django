from django.urls import path

from . import views

app_name = "elections"

urlpatterns = [
    path("", views.election_detail, name="detail"),
    path("statement/", views.CandidacyEditView.as_view(), name="statement"),
]
