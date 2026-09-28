from django.urls import path

from .views import ChecklistDetailView, MentionSuggestionsView, ProcessIndexView, ProcessObjectListView

urlpatterns = [
    path("", ProcessIndexView.as_view(), name="checklists-index"),
    path("mentions/", MentionSuggestionsView.as_view(), name="checklists-mentions"),
    path("<str:app_label>/<str:model_name>/", ProcessObjectListView.as_view(), name="checklists-object-list"),
    path(
        "<str:app_label>/<str:model_name>/<int:object_id>/",
        ChecklistDetailView.as_view(),
        name="checklists-detail",
    ),
]
