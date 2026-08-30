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
