from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings


class AccountAdapter(DefaultAccountAdapter):
    """Derives a username from the email, since signup only collects email."""

    def is_open_for_signup(self, request):
        return getattr(settings, "ACCOUNT_ALLOW_SIGNUPS", True)

    def populate_username(self, request, user):
        if not user.username:
            base = (user.email or "").split("@")[0] or "member"
            user.username = self.generate_unique_username([base])


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Keeps Discord connect-only.

    Members sign up with an emailed code; Discord is something they link
    afterwards to receive the messaging role. Returning False here means an
    unrecognised Discord login cannot create an account — the OAuth flow only
    succeeds as a `connect` from an already signed-in member.
    """

    def is_open_for_signup(self, request, sociallogin):
        return False
