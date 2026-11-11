"""Public job pages and the sponsor-champion jobs console (issue #224).

Two surfaces share the Job model:

* `/jobs/` and `/jobs/<pk>/` are public, read-only pages rendering only the
  allowlisted public fields of a published job — no login, GET/HEAD only.
* `/jobs/manage/` is a neapolitan CRUD console a sponsor champion uses to
  manage postings for the sponsor they represent. Every object lookup is
  scoped to `request.user.corporation_affiliate`, so a champion can never see
  or touch another sponsor's job (see the security note on #224).

A third, narrow entry point (issue #231) lets a corporate-sponsorship manager
add a single job for a sponsor straight from that sponsor's console page,
without needing the champion role.
"""

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_safe
from django.views.generic import CreateView
from neapolitan.views import CRUDView

from core.models import CORPORATE_SPONSOR_PERMS
from corporate_sponsorships.models import Sponsor

from .forms import JobForm
from .models import JOB_CHAMPION_PERMS, Job, can_champion_jobs


def _public_job(job):
    """Reduce a Job to a dict of allowlisted, render-safe values.

    Built from `Job.PUBLIC_FIELDS` with the sponsor object replaced by just
    its name and URL, so a template can never reach through to Sponsor
    internals (contract amount, invoice date, primary contact, notes).
    """
    data = job.get_public_data()
    sponsor = data.pop("sponsor")
    data["sponsor_name"] = sponsor.name
    data["sponsor_url"] = sponsor.url
    data["employment_type_display"] = job.get_employment_type_display()
    return data


@require_safe
def job_list(request):
    """Public list of published jobs."""
    jobs = [_public_job(job) for job in Job.objects.public().select_related("sponsor")]
    return render(request, "jobs/public_job_list.html", {"jobs": jobs})


@require_safe
def job_detail(request, pk):
    """Public detail page for one published job, or 404."""
    job = Job.objects.public().select_related("sponsor").filter(pk=pk).first()
    if job is None:
        raise Http404
    return render(request, "jobs/public_job_detail.html", {"job": _public_job(job)})


class ChampionScopeMixin:
    """Gate and scope every champion request to the user's own sponsor.

    Runs after LoginRequiredMixin/PermissionRequiredMixin (see the MRO on
    JobChampionView): an anonymous visitor is redirected to login, a member
    without the full permission set gets a 403, and an authenticated user who
    holds the perms but is not a corporate sponsor with an affiliation gets a
    404 rather than a partial console.
    """

    def dispatch(self, request, *args, **kwargs):
        if not can_champion_jobs(request.user):
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        """Every list/detail/edit/delete lookup comes from this scope only."""
        return Job.objects.filter(sponsor=self.request.user.corporation_affiliate)


class JobChampionView(LoginRequiredMixin, PermissionRequiredMixin, ChampionScopeMixin, CRUDView):
    """Sponsor-champion console at /jobs/manage/.

    Full CRUD on the champion's own sponsor's jobs. `permission_required` is
    the same full set `can_champion_jobs` checks; the sponsor is set from the
    user in `form_valid`, never from the request.
    """

    model = Job
    url_base = "jobs/manage"
    form_class = JobForm
    fields = [
        "title",
        "description",
        "apply_url",
        "location",
        "remote",
        "employment_type",
        "status",
        "is_published",
    ]
    filterset_fields = ["status", "is_published", "remote", "employment_type"]
    paginate_by = 25
    permission_required = list(JOB_CHAMPION_PERMS)

    def form_valid(self, form):
        """Pin the job to the champion's sponsor and stamp published_at once.

        Any `sponsor` field in the POST is ignored because JobForm does not
        expose it; the owning sponsor is always the user's affiliation.
        """
        form.instance.sponsor = self.request.user.corporation_affiliate
        if form.instance.is_published and form.instance.published_at is None:
            form.instance.published_at = timezone.now()
        return super().form_valid(form)


class SponsorJobCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Create one job for a sponsor from the corporate-sponsor console (issue #231).

    Community reps who manage sponsors can add a one-time posting for a
    sponsor without becoming job champions. Access is gated on the same full
    corporate-sponsor permission set as `SponsorView`, so reaching this view
    is equivalent to being allowed to edit the sponsor it writes to.

    The owning sponsor always comes from the `sponsor_pk` in the URL, never
    from the POST: `JobForm` exposes no `sponsor` field, so a `sponsor` id
    submitted in the body is ignored and a job can never be bound to a
    company the requester did not explicitly open.
    """

    model = Job
    form_class = JobForm
    template_name = "jobs/sponsor_job_form.html"
    permission_required = list(CORPORATE_SPONSOR_PERMS)

    def dispatch(self, request, *args, **kwargs):
        # Resolve the sponsor up front so both GET and POST 404 the same way
        # for an unknown pk, and so the template can name it.
        self.sponsor = Sponsor.objects.filter(pk=kwargs["sponsor_pk"]).first()
        if self.sponsor is None:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """Pin the job to the URL's sponsor and stamp `published_at` once."""
        form.instance.sponsor = self.sponsor
        if form.instance.is_published and form.instance.published_at is None:
            form.instance.published_at = timezone.now()
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sponsor"] = self.sponsor
        return context

    def get_success_url(self):
        return reverse("corporate-sponsors-detail", args=[self.sponsor.pk])
