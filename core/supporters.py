"""Accounts and import handling for foundational supporters.

Support hangs off a user account, so importing a roster means resolving each
line to a user. Two cases:

* **With an email** — the real thing. The account is created unverified, which
  makes it self-claiming: the supporter signs in with an emailed code, allauth
  verifies the address on the way through, and the account is theirs with its
  support history attached. No admin step.
* **Without an email** — a placeholder on a reserved `.invalid` domain (RFC
  2606, so nothing is ever deliverable there) with an unusable password. The
  account holds the history but cannot be signed into, and is superseded the
  moment the same person is re-imported with a real address.

`get_or_create_supporter_user` takes the User model as an argument because a
migration calls it with a historical model.
"""

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils.text import slugify

SUPPORTER_EMAIL_DOMAIN = "supporters.blackpythondevs.invalid"


def placeholder_email(name, suffix=""):
    """Deterministic non-deliverable address for a supporter's name."""
    slug = slugify(name) or "supporter"
    return f"{slug}{suffix}@{SUPPORTER_EMAIL_DOMAIN}"


def is_placeholder(user):
    return user.email.endswith(f"@{SUPPORTER_EMAIL_DOMAIN}")


def _unique_username(User, base):
    username = base
    counter = 1
    while User.objects.filter(username=username).exists():
        counter += 1
        username = f"{base}-{counter}"
    return username


def get_or_create_supporter_user(User, name, email=""):
    """Return `(user, created)` for one supporter, reusing any account we hold.

    Given a real email, that address is the identity: an existing account with
    it is reused as-is, and a placeholder previously made for the same name is
    upgraded in place rather than left behind as a duplicate, so the support
    history follows the person to their claimable account.
    """
    email = (email or "").strip()
    name = (name or "").strip()

    if email:
        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            # Never overwrite a name someone chose for themselves.
            if name and not existing.display_name:
                existing.display_name = name
                existing.save(update_fields=["display_name"])
            return existing, False

        if name and (placeholder := _find_placeholder(User, name)):
            placeholder.email = email
            placeholder.username = _unique_username(User, email.split("@")[0])
            placeholder.save(update_fields=["email", "username"])
            return placeholder, False
    elif name and (placeholder := _find_placeholder(User, name)):
        return placeholder, False

    if not email:
        suffix = ""
        counter = 1
        while User.objects.filter(email=placeholder_email(name, suffix)).exists():
            counter += 1
            suffix = f"-{counter}"
        email = placeholder_email(name, suffix)

    # `make_password(None)` rather than `set_unusable_password()`: this also runs
    # against the historical User model in a migration, which has fields but no
    # methods.
    user = User.objects.create(
        username=_unique_username(User, email.split("@")[0]),
        email=email,
        display_name=name,
        password=make_password(None),
    )
    return user, True


def _find_placeholder(User, name):
    """An unclaimed account previously minted for this exact display name."""
    return User.objects.filter(
        display_name=name,
        email__endswith=f"@{SUPPORTER_EMAIL_DOMAIN}",
    ).first()


@transaction.atomic
def import_supporters(rows, *, clear=False):
    """Load supporter records, optionally replacing the roster wholesale.

    `rows` are dicts of `name`, `email`, `year`, `status`. With `clear`, every
    existing support record goes first and placeholder accounts left with no
    support are deleted — real accounts are always kept, since a member who
    also donated is not ours to delete.

    Runs in one transaction, so a bad line partway through a re-upload leaves
    the existing roster untouched rather than half-replaced.
    """
    from django.contrib.auth import get_user_model

    from core.models import FoundationalSupport

    User = get_user_model()
    stats = {"support": 0, "users_created": 0, "support_deleted": 0, "users_deleted": 0}

    if clear:
        stats["support_deleted"] = FoundationalSupport.objects.all().delete()[0]

    for row in rows:
        user, created = get_or_create_supporter_user(User, row.get("name", ""), row.get("email", ""))
        stats["users_created"] += int(created)
        FoundationalSupport.objects.update_or_create(
            user=user,
            year=int(row["year"]),
            defaults={
                "status": row.get("status") or FoundationalSupport.LISTED,
                "note": row.get("note") or "",
            },
        )
        stats["support"] += 1

    if clear:
        orphans = User.objects.filter(
            email__endswith=f"@{SUPPORTER_EMAIL_DOMAIN}",
            foundational_support__isnull=True,
            is_staff=False,
            is_superuser=False,
        )
        # Counted before deleting: `delete()` reports cascaded rows too.
        stats["users_deleted"] = orphans.count()
        orphans.delete()

    return stats
