"""Keep the "Community Admins" auth group in step with CommunityAdmin rows.

Membership in that group is what grants access to the front-end console (see
views.py's `PermissionRequiredMixin` check) — a user belongs to it exactly
while they admin at least one community. We sync on every save and delete so
adding or removing a CommunityAdmin row takes effect immediately, the same
pattern ambassadors/signals.py uses for the Ambassadors group.
"""

import logging

from django.contrib.auth.models import Group
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import COMMUNITY_ADMIN_GROUP_NAME, CommunityAdmin

logger = logging.getLogger(__name__)


def _sync_membership(user):
    group = Group.objects.filter(name=COMMUNITY_ADMIN_GROUP_NAME).first()
    if group is None:
        # The data migration provisions this group; if it's somehow missing we
        # log rather than crash a save.
        logger.warning("%r group not found; skipping membership sync", COMMUNITY_ADMIN_GROUP_NAME)
        return

    if CommunityAdmin.objects.filter(user=user).exists():
        group.user_set.add(user)
    else:
        group.user_set.remove(user)


@receiver(post_save, sender=CommunityAdmin)
def sync_group_on_save(sender, instance, **kwargs):
    _sync_membership(instance.user)


@receiver(post_delete, sender=CommunityAdmin)
def sync_group_on_delete(sender, instance, **kwargs):
    _sync_membership(instance.user)
