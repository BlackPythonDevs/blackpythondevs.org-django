from django.urls import path

from . import views

app_name = "ambassadors"

urlpatterns = [
    path("apply/", views.ApplyView.as_view(), name="apply"),
    path("status/", views.StatusView.as_view(), name="status"),
]
