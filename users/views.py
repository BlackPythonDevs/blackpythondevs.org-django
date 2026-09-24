from allauth.account.internal.flows.login_by_code import LoginCodeVerificationProcess
from allauth.core.internal.httpkit import headed_redirect_response
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ambassadors.models import StudentAmbassador
from communities.models import can_manage_community
from community_messages.models import is_leadership
from core.models import CustomImage, Leader, is_council_member, is_leadership_or_above
from elections.models import Election
from nominations.models import can_nominate
from notifications.models import can_send_notifications

from .discord import is_configured, login_available
from .forms import CouncilProfileForm, OnboardingForm, ProfileForm
from .models import INVITE_SESSION_KEY, InviteLink


@login_required
def members(request):
    """The member area: profile summary and Discord connection status."""
    if request.user.needs_onboarding:
        return redirect("onboarding")

    # The latest election cycle, if one's been set up — drives the Council
    # election panel below (see elections.management.commands.create_election).
    election = Election.objects.order_by("-year").first()

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
            # Council members get the election panel; only they can be candidates.
            "is_council_member": is_council_member(request.user),
            "current_election": election,
            "can_write_candidacy_statement": election is not None and election.phase == Election.NOMINATING,
            # Staff, Executors, Sponsors, and Community Partners get the notifications panel.
            "can_send_notifications": can_send_notifications(request.user),
            # Community admins get a link to their console + compose form.
            "can_manage_communities": can_manage_community(request.user),
            # Leadership members get a link to messages sent to them.
            "is_leadership_member": is_leadership(request.user),
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


@login_required
def profile(request):
    """Lets a signed-in member update their name and onboarding answers anytime,
    not just on the one-time onboarding survey. Leadership and above also get
    the social links fields here (see `core.models.is_leadership_or_above`).
    """
    include_social = is_leadership_or_above(request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user, include_social=include_social)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("members")
    else:
        form = ProfileForm(instance=request.user, include_social=include_social)

    return render(request, "users/profile.html", {"form": form})


def invite_accept(request, token):
    """Landing page for an invite link.

    An email-locked invite is confirmed directly here: accepting applies its groups
    to the (found-or-created) account for that email, then hands off to allauth's
    own login-by-code flow — same as an existing member signing up again in
    users.forms.SignupForm.

    A general-purpose signup link (no fixed email) instead hands off to the normal
    signup form, stashing its token in the session — SignupForm applies this
    invite's groups once that form finds or creates an account, whichever email
    the visitor enters.
    """
    invite = get_object_or_404(InviteLink, token=token)

    if not invite.is_valid:
        return render(request, "users/invite_accept.html", {"invite": invite, "invalid": True})

    if not invite.email:
        request.session[INVITE_SESSION_KEY] = invite.token
        return redirect("account_signup")

    if request.method == "POST":
        user = invite.accept(request)
        LoginCodeVerificationProcess.initiate(request=request, user=user, email=invite.email)
        return headed_redirect_response("account_confirm_login_code")

    return render(request, "users/invite_accept.html", {"invite": invite, "invalid": False})
