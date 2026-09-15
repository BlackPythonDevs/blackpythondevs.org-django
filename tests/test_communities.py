"""Communities: region derivation, the community-admin console, self-service
leaving, and messaging leadership.

The console (/communities/…) is scoped two ways at once: PermissionRequiredMixin
gates on the "Community Admins" group's view/change permissions (so outsiders
get 403, not a login bounce), and CommunityAdminConsole.get_queryset() further
restricts a member of that group to only the communities they actually admin
(so a wrong community is a 404, not a 403). There's no create or delete role
at all — staff manage those in the Django admin.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.utils import timezone

from communities.models import COMMUNITY_ADMIN_GROUP_NAME, Community, CommunityAdmin, CommunityMessage
from core.models import LEADERSHIP_GROUP_NAME

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def required_groups(db):
    for name in (COMMUNITY_ADMIN_GROUP_NAME, LEADERSHIP_GROUP_NAME):
        Group.objects.get_or_create(name=name)


def make_user(username, **kwargs):
    kwargs.setdefault("onboarding_completed_at", timezone.now())
    return get_user_model().objects.create_user(
        username=username, email=f"{username}@example.com", password="pw", **kwargs
    )


def make_leader(username, country):
    """A user in the Leadership group, with `region` naturally derived from
    `country` (never set directly — it must go through the same derivation
    Community.region does, so the two are comparable)."""
    user = make_user(username, country=country)
    user.groups.add(Group.objects.get(name=LEADERSHIP_GROUP_NAME))
    return user


@pytest.fixture
def community(db):
    return Community.objects.create(name="PyLagos", country="NG")


@pytest.fixture
def admin_user(db, community):
    user = make_user("admin")
    CommunityAdmin.objects.create(community=community, user=user)
    return user


@pytest.fixture
def member(db):
    return make_user("member")


class TestRegionDerivation:
    def test_region_is_derived_from_country(self, db):
        community = Community.objects.create(name="PyLagos", country="NG")
        assert community.region == "Western Africa"

    def test_online_overrides_country_derived_region(self, db):
        community = Community.objects.create(name="Remote Pythonistas", is_online=True, country="NG")
        assert community.region == "Online"

    def test_region_matches_user_region_taxonomy(self, db):
        """Community.region must speak the same taxonomy as User.region —
        both come from users.regions, not sponsorships.regions (which uses
        coarse continent names like "Africa" instead of "Western Africa")."""
        community = Community.objects.create(name="PyLagos", country="NG")
        user = make_user("leader", country="NG")
        assert community.region == user.region


class TestGroupSync:
    def test_creating_community_admin_grants_group(self, db, community, member):
        assert not member.groups.filter(name=COMMUNITY_ADMIN_GROUP_NAME).exists()
        CommunityAdmin.objects.create(community=community, user=member)
        assert member.groups.filter(name=COMMUNITY_ADMIN_GROUP_NAME).exists()

    def test_removing_last_admin_link_revokes_group(self, db, community, member):
        link = CommunityAdmin.objects.create(community=community, user=member)
        link.delete()
        assert not member.groups.filter(name=COMMUNITY_ADMIN_GROUP_NAME).exists()

    def test_admin_of_a_second_community_keeps_group_after_leaving_first(self, db, community, member):
        other = Community.objects.create(name="Djangonauts", country="US")
        CommunityAdmin.objects.create(community=community, user=member).delete()
        CommunityAdmin.objects.create(community=other, user=member)
        CommunityAdmin.objects.filter(community=community, user=member).delete()
        assert member.groups.filter(name=COMMUNITY_ADMIN_GROUP_NAME).exists()


class TestConsoleAccess:
    def test_admin_reaches_own_community(self, client, admin_user, community):
        client.force_login(admin_user)
        for url in (
            "/communities/",
            f"/communities/{community.pk}/",
            f"/communities/{community.pk}/edit/",
        ):
            assert client.get(url).status_code == 200, url

    def test_anonymous_is_bounced(self, client, community):
        assert client.get(f"/communities/{community.pk}/").status_code == 302

    def test_ordinary_member_gets_403(self, client, member, community):
        client.force_login(member)
        assert client.get(f"/communities/{community.pk}/").status_code == 403

    def test_admin_of_another_community_gets_404_not_403(self, client, admin_user, community):
        """The group grants view/change generally; get_queryset() scopes to
        the admin's own community, so a wrong community 404s instead of 403ing."""
        other = Community.objects.create(name="Djangonauts", country="US")
        client.force_login(admin_user)
        assert client.get(f"/communities/{other.pk}/").status_code == 404

    def test_no_create_or_delete_routes_exist(self, client, admin_user, community):
        client.force_login(admin_user)
        assert client.get("/communities/new/").status_code == 404
        assert client.get(f"/communities/{community.pk}/delete/").status_code == 404


class TestLeaving:
    def test_admin_can_leave_their_own_community(self, client, admin_user, community):
        client.force_login(admin_user)
        response = client.post(f"/communities/{community.pk}/leave/")
        assert response.status_code == 302
        assert not CommunityAdmin.objects.filter(community=community, user=admin_user).exists()

    def test_cannot_leave_a_community_you_do_not_admin(self, client, member, community):
        client.force_login(member)
        assert client.post(f"/communities/{community.pk}/leave/").status_code == 404

    def test_leaving_never_deletes_the_community(self, client, admin_user, community):
        client.force_login(admin_user)
        client.post(f"/communities/{community.pk}/leave/")
        assert Community.objects.filter(pk=community.pk).exists()


class TestMessageRecipients:
    def test_filters_by_community_region_not_sender_region(self, db, community, admin_user):
        """The sending admin's own User.region must never factor in — only
        the community's region does."""
        admin_user.country = "US"  # a different region than the community's
        admin_user.save()
        matching_leader = make_leader("lead-ng", "NG")  # same country as the community
        other_leader = make_leader("lead-us", "US")

        message = CommunityMessage.objects.create(community=community, sender=admin_user, subject="Hi", body="Hello")
        recipients = set(message.recipients())

        assert matching_leader in recipients
        assert other_leader not in recipients
        assert admin_user not in recipients  # not in the Leadership group at all

    def test_online_community_reaches_every_region(self, db, admin_user):
        online_community = Community.objects.create(name="Remote Pythonistas", is_online=True)
        CommunityAdmin.objects.create(community=online_community, user=admin_user)
        leader_a = make_leader("lead-a", "NG")
        leader_b = make_leader("lead-b", "US")

        message = CommunityMessage.objects.create(
            community=online_community, sender=admin_user, subject="Hi", body="Hello"
        )
        recipients = set(message.recipients())

        assert leader_a in recipients
        assert leader_b in recipients

    def test_only_leadership_group_members_receive(self, db, community, admin_user):
        make_user("bystander", country="NG")  # same region as the community, but not in Leadership
        message = CommunityMessage.objects.create(community=community, sender=admin_user, subject="Hi", body="Hello")
        assert message.recipients().count() == 0


class TestSendMessageView:
    def test_admin_can_send_to_matching_leadership(self, client, admin_user, community):
        leader = make_leader("lead-ng", "NG")  # same country as the community
        client.force_login(admin_user)
        response = client.post(
            "/communities/messages/send/",
            {"community": community.pk, "subject": "Update", "body": "Things are happening."},
        )
        assert response.status_code == 302, response.context["form"].errors if response.context else ""
        sent = CommunityMessage.objects.get(subject="Update")
        assert sent.sent_at is not None
        assert sent.recipient_count == 1
        assert len(mail.outbox) == 1
        assert mail.outbox[0].bcc == [leader.email]

    def test_form_only_offers_communities_the_sender_admins(self, client, admin_user, community):
        Community.objects.create(name="Not mine", country="US")
        client.force_login(admin_user)
        response = client.get("/communities/messages/send/")
        assert list(response.context["form"].fields["community"].queryset) == [community]

    def test_non_admin_gets_403(self, client, member):
        client.force_login(member)
        assert client.get("/communities/messages/send/").status_code == 403
