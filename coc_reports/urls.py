from django.urls import path

from .views import CocReportDetailView, CocReportDoneView, CocReportListView, PublicCocReportView

# Included under "coc/" from bpd/urls.py.
urlpatterns = [
    # Public intake — open to anonymous visitors.
    path("report/", PublicCocReportView.as_view(), name="coc-report"),
    path("report/thanks/", CocReportDoneView.as_view(), name="coc-report-done"),
    # The CoC team's console — COC Report Viewing role only.
    path("reports/", CocReportListView.as_view(), name="coc-report-list"),
    path("reports/<int:pk>/", CocReportDetailView.as_view(), name="coc-report-detail"),
]
