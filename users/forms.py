"""Signup form overrides.

The site is passwordless: everyone signs in with a one-time emailed code. That
breaks a corner of allauth's default signup flow. When someone submits the
signup form with an email address that already has an account, allauth's
enumeration-prevention path emails them an "account already exists" notice that
tells them to *reset their password* — advice that makes no sense here, since
there are no passwords. Worse, the browser is left on the code-entry page
waiting for a code that was never sent.

`SignupForm` below intercepts that case: instead of the password-reset notice,
it sends the existing member a login code and sends the browser to the same
code-confirmation page the login flow uses. Signing up with an address you
already registered simply logs you in.
"""

from allauth.account.forms import SignupForm as AllauthSignupForm
from allauth.account.internal.flows.login_by_code import LoginCodeVerificationProcess
from allauth.account.utils import filter_users_by_email
from allauth.core.internal.httpkit import headed_redirect_response
from django import forms

from core.models import Leader

from .models import User


class SignupForm(AllauthSignupForm):
    def try_save(self, request):
        if self.account_already_exists:
            email = self.cleaned_data.get("email")
            users = filter_users_by_email(email, prefer_verified=True)
            if users:
                LoginCodeVerificationProcess.initiate(
                    request=request, user=users[0], email=email
                )
                return None, headed_redirect_response("account_confirm_login_code")
        return super().try_save(request)


class OnboardingForm(forms.ModelForm):
    """The new-member survey shown once, right after signup."""

    member_type = forms.ChoiceField(
        choices=User.MEMBER_TYPE_CHOICES,
        widget=forms.RadioSelect,
        label="Do you identify as a BPD Member or a Friend/Supporter/Ally?",
    )
    subcommunities = forms.MultipleChoiceField(
        choices=User.SUBCOMMUNITY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Do you identify as a member of any of the following communities?",
        help_text="We'll let you know about opportunities for folks in these subcommunities.",
    )
    communication_preferences = forms.MultipleChoiceField(
        choices=User.COMMUNICATION_PREFERENCE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Do you want to hear about the following?",
    )

    class Meta:
        model = User
        fields = ["member_type", "country", "subcommunities", "communication_preferences"]
        labels = {"country": "What country do you currently reside in?"}
        help_texts = {"country": "We'll match this to a region behind the scenes."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # CountryField is blank=True on the model (it stays optional for
        # accounts created outside onboarding); the onboarding step itself
        # asks it as one of the required questions.
        self.fields["country"].required = True


class CouncilProfileForm(forms.ModelForm):
    """The extra step shown to Leadership Council members: photo and affiliations.

    `photo` is a plain upload, not the model's `photo` FK to a Wagtail image —
    the view turns an uploaded file into a `CustomImage` and assigns that FK
    itself, since a ModelForm can't do that translation on save().
    """

    photo = forms.ImageField(required=False, help_text="A photo for the public leadership roster.")

    class Meta:
        model = Leader
        fields = ["affiliations"]
        help_texts = {
            "affiliations": "Other organizations or communities you're affiliated with.",
        }
