"""Keep the "Ambassadors" auth group in step with accepted applications.

The group is the roster of ambassadors: a member belongs to it exactly while
their application is accepted. We sync on every save and on delete so the
roster can't drift — promoting, demoting, rejecting, or deleting a record all
take effect immediately. Applications with no linked user (e.g. entered by hand
in the admin) are simply skipped; there's no one to add.
"""

import logging

from django.contrib.auth.models import Group
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import GROUP_NAME, StudentAmbassador

logger = logging.getLogger(__name__)


def _sync_membership(application, *, accepted):
    """Add or remove the application's user from the Ambassadors group."""
    user = application.user
    if user is None:
        return

    group = Group.objects.filter(name=GROUP_NAME).first()
    if group is None:
        # The data migration provisions this group; if it's somehow missing we
        # log rather than crash a save.
        logger.warning("Ambassadors group %r not found; skipping membership sync", GROUP_NAME)
        return

    if accepted:
        group.user_set.add(user)
    else:
        group.user_set.remove(user)


@receiver(post_save, sender=StudentAmbassador)
def sync_group_on_save(sender, instance, **kwargs):
    _sync_membership(instance, accepted=instance.is_accepted)


@receiver(post_delete, sender=StudentAmbassador)
def sync_group_on_delete(sender, instance, **kwargs):
    # A deleted application can never keep someone on the roster.
    _sync_membership(instance, accepted=False)
