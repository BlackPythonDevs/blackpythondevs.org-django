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


@pytest.mark.parametrize("name", [AMBASSADORS_GROUP_NAME, COUNCIL_GROUP_NAME, LEADERSHIP_GROUP_NAME])
def test_membership_groups_carry_no_permissions(name):
    """Membership groups must not silently grant admin access."""
    assert not Group.objects.get(name=name).permissions.exists()


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
