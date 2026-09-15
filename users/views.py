from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from ambassadors.models import StudentAmbassador
from core.models import CustomImage, Leader, is_council_member
from nominations.models import can_nominate

from .discord import is_configured, login_available
from .forms import CouncilProfileForm, OnboardingForm


@login_required
def members(request):
    """The member area: profile summary and Discord connection status."""
    if request.user.needs_onboarding:
        return redirect("onboarding")

    return render(
        request,
        "users/members.html",
        {
            "discord_account": SocialAccount.objects.filter(user=request.user, provider="discord").first(),
            "discord_invite_url": settings.DISCORD_INVITE_URL,
            # Whether connecting actually grants the messaging role, or just links.
            "discord_role_enabled": is_configured(),
            # Whether a Discord OAuth app exists, so the connect flow can run.
            "discord_login_available": login_available(request),
            # Their ambassador application, if they've started one.
            "ambassador_application": StudentAmbassador.objects.filter(user=request.user).first(),
            # Council/Leadership members get the nominations panel.
            "can_nominate": can_nominate(request.user),
        },
    )


@login_required
def onboarding(request):
    """One-time new-member survey. Council members also add a photo and affiliations."""
    council_member = is_council_member(request.user)
    leader = None
    if council_member:
        leader, _ = Leader.objects.get_or_create(
            user=request.user,
            defaults={
                "name": request.user.get_full_name() or request.user.display_name or request.user.email,
                "role": Leader.COUNCIL,
            },
        )

    if request.method == "POST":
        form = OnboardingForm(request.POST, instance=request.user)
        council_form = CouncilProfileForm(request.POST, request.FILES, instance=leader) if leader else None

        if form.is_valid() and (council_form is None or council_form.is_valid()):
            user = form.save(commit=False)
            user.onboarding_completed_at = timezone.now()
            user.save()

            if council_form is not None:
                council_leader = council_form.save(commit=False)
                photo_file = council_form.cleaned_data.get("photo")
                if photo_file:
                    council_leader.photo = CustomImage.objects.create(title=photo_file.name, file=photo_file)
                council_leader.save()

            messages.success(request, "Thanks — your profile is all set.")
            return redirect("members")
    else:
        form = OnboardingForm(instance=request.user)
        council_form = CouncilProfileForm(instance=leader) if leader else None

    return render(request, "users/onboarding.html", {"form": form, "council_form": council_form})
