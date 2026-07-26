"""Auth pages render outside Wagtail, where no `page` is in the context.

These regression-test the template lookups that used to 500 there.
"""

import pytest

pytestmark = pytest.mark.django_db

User = None


@pytest.fixture(autouse=True)
def _load_user_model():
    global User
    from django.contrib.auth import get_user_model

    User = get_user_model()


@pytest.mark.parametrize("path", ["/accounts/login/", "/accounts/signup/"])
def test_auth_pages_render(client, site, path):
    response = client.get(path)
    assert response.status_code == 200
    # Site chrome is present, so these extend the real base template.
    assert "Black Python Devs" in response.content.decode()


def test_auth_page_falls_back_to_default_meta_description(client, site):
    html = client.get("/accounts/login/").content.decode()
    assert "Helping build communities for Black Pythonistas" in html


def test_signup_creates_user_with_generated_username(client, site):
    response = client.post(
        "/accounts/signup/",
        {"email": "member@example.com", "password1": "s3cure-passphrase!", "password2": "s3cure-passphrase!"},
    )
    assert response.status_code in (200, 302)
    user = User.objects.get(email="member@example.com")
    assert user.username, "AccountAdapter should derive a username from the email"


def test_login_uses_email(client, site):
    User.objects.create_user(username="someone", email="someone@example.com", password="s3cure-passphrase!")
    response = client.post(
        "/accounts/login/", {"login": "someone@example.com", "password": "s3cure-passphrase!"}
    )
    assert response.status_code == 302
