"""Who a checklist task can be assigned to.

Kept independent of any real project's group model, the same way registry.py
keeps this app from naming a consumer model: "assignable" here just means
"already holds this app's own `checklists.change_task` permission" — the
same permission PERMISSION_REQUIRED (views.py) demands to use the console at
all. Whichever group a project grants that to (in this one, the "Executor"
group — see migrations/0002_executor_group.py) is automatically who shows up
in the assignment dropdown, with no group name hardcoded here.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models import Q


def assignable_users():
    permission = Permission.objects.filter(codename="change_task", content_type__app_label="checklists").first()
    if permission is None:
        return get_user_model().objects.none()
    return (
        get_user_model()
        .objects.filter(Q(is_superuser=True) | Q(groups__permissions=permission) | Q(user_permissions=permission))
        .distinct()
        .order_by("email")
    )


def display_label(user):
    """A person's label everywhere this app shows one: their `@username`
    (what you'd actually type to mention them) first, falling back to a
    display name if a project's User model has one and it's set, and finally
    to `str(user)` so this never renders blank. Deliberately not
    `User.__str__` itself, which most projects (this one included) point at
    email/full name first — that's a site-wide default this app doesn't own.
    """
    if user is None:
        return ""
    return user.username or getattr(user, "display_name", "") or str(user)
