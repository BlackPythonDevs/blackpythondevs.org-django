"""Public front-end for the student ambassador programme.

Applying requires being signed in: every application ties back to a member so
the Ambassadors group roster stays accurate once an application is accepted. A
member has at most one application — if they've already applied, both views
send them to their status page instead of a second form.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView

from .forms import AmbassadorApplicationForm
from .models import StudentAmbassador


class ApplyView(LoginRequiredMixin, CreateView):
    """The application form. One application per member."""

    form_class = AmbassadorApplicationForm
    template_name = "ambassadors/apply.html"
    success_url = reverse_lazy("ambassadors:status")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and _existing_application(request.user):
            return redirect("ambassadors:status")
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        # Prefill from the member's profile where we can.
        user = self.request.user
        return {"name": user.get_full_name() or user.display_name, "email": user.email}

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class StatusView(LoginRequiredMixin, TemplateView):
    """Shows the signed-in member their application and its current status."""

    template_name = "ambassadors/status.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not _existing_application(request.user):
            return redirect("ambassadors:apply")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["application"] = _existing_application(self.request.user)
        return context


def _existing_application(user):
    return StudentAmbassador.objects.filter(user=user).first()
