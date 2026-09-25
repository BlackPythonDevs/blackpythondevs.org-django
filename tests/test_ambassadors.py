"""Student ambassadors: applying, status lifecycle, and the group roster.

Accepted applications put the member in the "Ambassadors" group; anything else
keeps them out. Waitlisting is just a status. The application form requires a
signed-in member so every record ties back to a user.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from ambassadors.models import GROUP_NAME, StudentAmbassador

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def ambassadors_group(db):
    # The data migration creates this in the real DB; ensure it exists for the
    # in-memory test DB too.
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    return group


@pytest.fixture
def member(db):
    return get_user_model().objects.create_user(
        username="stu", email="stu@example.com", password="pw", display_name="Stu Dent"
    )


def make(user=None, **kwargs):
    defaults = {
        "name": "Stu Dent",
        "email": "stu@example.com",
        "school": "State University",
        "motivation": "I want to grow the community.",
    }
    defaults.update(kwargs)
    return StudentAmbassador.objects.create(user=user, **defaults)


class TestGroupSync:
    def test_accepted_application_adds_user_to_group(self, member, ambassadors_group):
        make(user=member, status=StudentAmbassador.ACCEPTED)
        assert ambassadors_group in member.groups.all()

    def test_applied_and_waitlisted_stay_out_of_group(self, member, ambassadors_group):
        app = make(user=member, status=StudentAmbassador.APPLIED)
        assert ambassadors_group not in member.groups.all()

        app.status = StudentAmbassador.WAITLISTED
        app.save()
        assert ambassadors_group not in member.groups.all()

    def test_moving_off_accepted_removes_from_group(self, member, ambassadors_group):
        app = make(user=member, status=StudentAmbassador.ACCEPTED)
        assert ambassadors_group in member.groups.all()

        app.status = StudentAmbassador.REJECTED
        app.save()
        assert ambassadors_group not in member.groups.all()

    def test_deleting_accepted_application_removes_from_group(self, member, ambassadors_group):
        app = make(user=member, status=StudentAmbassador.ACCEPTED)
        assert ambassadors_group in member.groups.all()

        app.delete()
        member.refresh_from_db()
        assert ambassadors_group not in member.groups.all()

    def test_application_without_user_does_not_crash(self, ambassadors_group):
        # Admin-entered record with no member attached: sync is a no-op.
        app = make(status=StudentAmbassador.ACCEPTED)
        assert app.pk is not None


class TestApplyView:
    def test_anonymous_is_redirected_to_login(self, client):
        response = client.get("/student-ambassadors/apply/")
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def test_member_can_submit_application(self, client, member, ambassadors_group):
        client.force_login(member)
        response = client.post(
            "/student-ambassadors/apply/",
            {
                "name": "Stu Dent",
                "email": "stu@example.com",
                "school": "State University",
                "field_of_study": "Computer Science",
                "graduation_year": 2027,
                "country": "US",
                "motivation": "I want to grow the community.",
            },
        )
        assert response.status_code == 302
        assert response["Location"] == "/student-ambassadors/status/"

        app = StudentAmbassador.objects.get(user=member)
        assert app.status == StudentAmbassador.APPLIED
        assert app.school == "State University"

    def test_second_application_redirects_to_status(self, client, member, ambassadors_group):
        make(user=member)
        client.force_login(member)
        response = client.get("/student-ambassadors/apply/")
        assert response.status_code == 302
        assert response["Location"] == "/student-ambassadors/status/"


class TestApplyBlock:
    """The Wagtail block renders a button pointing at the native apply form."""

    @pytest.fixture
    def site(self, bootstrapped_site):
        """Needs the real StandardPage bootstrap_site seeds at this slug."""
        return bootstrapped_site

    def test_block_renders_apply_link(self, client, site):
        from home.models import StandardPage

        # bootstrap_site already creates this page; drop the block into its body.
        page = StandardPage.objects.get(slug="student-ambassador-program")
        page.body = [("ambassador_apply", {"heading": "Apply", "button_text": "Apply Now"})]
        page.save_revision().publish()

        html = client.get(page.url).content.decode()
        assert 'href="/student-ambassadors/apply/"' in html
        assert "Apply Now" in html


class TestStatusView:
    def test_status_page_shows_current_status(self, client, member, ambassadors_group):
        make(user=member, status=StudentAmbassador.WAITLISTED)
        client.force_login(member)
        html = client.get("/student-ambassadors/status/").content.decode()
        assert "Waitlisted" in html

    def test_status_without_application_redirects_to_apply(self, client, member):
        client.force_login(member)
        response = client.get("/student-ambassadors/status/")
        assert response.status_code == 302
        assert response["Location"] == "/student-ambassadors/apply/"
