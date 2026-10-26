"""Views for CoC reports: public intake, then the CoC team's console.

The intake views are open to anonymous visitors (like
sponsorships.views.PublicSponsorshipRequestView): whoever needs to file a
report should be able to, logged in or not. The submitting user is still
captured when there is one.

The console views are gated on the COC Report Viewing role's model
permissions (see migration 0002): view to read, change to close a report.
There is no create and no delete here on purpose — reports are made on the
public form and cannot be un-created.
"""

from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from notifications.models import notify

from .forms import CocReportForm, CocReportStatusForm
from .models import CocReport


class PublicCocReportView(CreateView):
    """The public "report a Code of Conduct violation" form.

    Deliberately open to anonymous visitors. The submitting user is captured
    onto `reporter` — anonymous or not — so the CoC team can notify them of
    the outcome; the model is excluded from django-auditlog precisely so
    nothing else logs who filed it (see coc_reports.models).
    """

    model = CocReport
    form_class = CocReportForm
    template_name = "coc_reports/report_form.html"
    success_url = reverse_lazy("coc-report-done")

    def form_valid(self, form):
        form.instance.reporter = self.request.user if self.request.user.is_authenticated else None
        return super().form_valid(form)


class CocReportDoneView(TemplateView):
    template_name = "coc_reports/report_done.html"


class CocReportListView(PermissionRequiredMixin, ListView):
    """Every report, newest first, for holders of the viewing role."""

    model = CocReport
    permission_required = "coc_reports.view_cocreport"
    template_name = "coc_reports/report_list.html"
    context_object_name = "reports"
    paginate_by = 25


class CocReportDetailView(PermissionRequiredMixin, DetailView):
    """One report: its description, its checklist, and the close-out form.

    `reporter` is deliberately never in the context — the template cannot
    render what isn't there. Closing a report requires change permission and
    notifies the captured reporter (a generic message with no link: the
    console they'd be linked to is role-gated and not theirs to open).
    """

    model = CocReport
    permission_required = "coc_reports.view_cocreport"
    template_name = "coc_reports/report_detail.html"
    context_object_name = "report"

    def post(self, request, *args, **kwargs):
        report = self.get_object()
        if not request.user.has_perm("coc_reports.change_cocreport"):
            raise PermissionDenied("Closing a report needs the COC Report Viewing role's change permission.")

        previous_status = report.status
        form = CocReportStatusForm(request.POST, instance=report)
        if form.is_valid():
            report = form.save()
            if report.status != previous_status and report.reporter:
                notify(
                    report.reporter,
                    f"Your Code of Conduct report has an update: it is now “{report.get_status_display()}”.",
                )
            messages.success(request, f"{report} is now “{report.get_status_display()}”.")
        else:
            for field_errors in form.errors.values():
                for error in field_errors:
                    messages.error(request, error)
        return redirect("coc-report-detail", pk=report.pk)

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "status_form": CocReportStatusForm(instance=self.object),
            "can_change": self.request.user.has_perm("coc_reports.change_cocreport"),
        }
