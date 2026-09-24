"""The auth groups that describe who someone is in the community.

Each is provisioned by a data migration so a fresh database and a long-running
one agree on the roster. These are membership groups — permissions, where they
exist, are asserted separately (see the Executor group below).
"""

import pytest
from django.contrib.auth.models import Group

from ambassadors.models import GROUP_NAME as AMBASSADORS_GROUP_NAME
from core.models import COUNCIL_GROUP_NAME, LEADERSHIP_GROUP_NAME

pytestmark = pytest.mark.django_db

EXECUTOR_GROUP_NAME = "Executor"


@pytest.mark.parametrize(
    "name",
    [AMBASSADORS_GROUP_NAME, COUNCIL_GROUP_NAME, LEADERSHIP_GROUP_NAME, EXECUTOR_GROUP_NAME],
)
def test_group_exists(name):
    assert Group.objects.filter(name=name).exists(), f"missing auth group {name!r}"


def test_ambassadors_group_carries_no_permissions():
    """Membership-only groups must not silently grant admin access."""
    assert not Group.objects.get(name=AMBASSADORS_GROUP_NAME).permissions.exists()


CMS_GROUP_NAMES = [COUNCIL_GROUP_NAME, LEADERSHIP_GROUP_NAME, EXECUTOR_GROUP_NAME]


@pytest.mark.parametrize("name", CMS_GROUP_NAMES)
def test_cms_groups_can_open_the_wagtail_admin(name):
    perms = Group.objects.get(name=name).permissions
    assert perms.filter(content_type__app_label="wagtailadmin", codename="access_admin").exists()


@pytest.mark.parametrize("name", CMS_GROUP_NAMES)
def test_cms_groups_edit_pages_but_cannot_publish(name):
    codenames = set(
        Group.objects.get(name=name).page_permissions.values_list("permission__codename", flat=True)
    )
    assert codenames == {"add_page", "change_page"}


@pytest.mark.parametrize("name", CMS_GROUP_NAMES)
def test_cms_groups_can_manage_images_and_documents(name):
    codenames = set(
        Group.objects.get(name=name).collection_permissions.values_list("permission__codename", flat=True)
    )
    assert {"add_customimage", "choose_customimage", "add_document", "choose_document"} <= codenames


@pytest.mark.django_db
def test_leadership_member_reaches_the_cms(client):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user("lead", password="x")
    user.groups.add(Group.objects.get(name=LEADERSHIP_GROUP_NAME))
    client.force_login(user)
    assert client.get("/cms/").status_code == 200


@pytest.mark.django_db
def test_ordinary_member_is_kept_out_of_the_cms(client):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user("plain", password="x")
    client.force_login(user)
    response = client.get("/cms/")
    assert response.status_code == 302 and "/cms/login" in response["Location"] or response.status_code == 403


def test_executor_group_keeps_its_sponsorship_permissions():
    codenames = set(
        Group.objects.get(name=EXECUTOR_GROUP_NAME).permissions.values_list("codename", flat=True)
    )
    assert {
        "add_sponsorshiprequest",
        "change_sponsorshiprequest",
        "delete_sponsorshiprequest",
        "view_sponsorshiprequest",
    } <= codenames
