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


def get_or_create_supporter_user(User, name, email="", *, match_name=True):
    """Return `(user, created)` for one supporter, reusing any account we hold.

    Given a real email, that address is the identity: an existing account with
    it is reused as-is, and a placeholder previously made for the same name is
    upgraded in place rather than left behind as a duplicate, so the support
    history follows the person to their claimable account.

    Only placeholders are ever matched on name. A *claimed* account sharing a
    name is left alone and a second account is made, because two people can
    have the same name and merging them silently is the worse mistake — see
    `find_name_conflicts`, which surfaces those for a human to decide. Pass
    `match_name=False` to force a new account even past a placeholder, which is
    how that decision is carried out.
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

        if match_name and name and (placeholder := _find_placeholder(User, name)):
            placeholder.email = email
            placeholder.username = _unique_username(User, email.split("@")[0])
            placeholder.save(update_fields=["email", "username"])
            return placeholder, False
    elif match_name and name and (placeholder := _find_placeholder(User, name)):
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


def _candidate_accounts(rows):
    """Every account a batch of rows could possibly land on, in two lookups."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    from django.db.models.functions import Lower

    User = get_user_model()
    emails = {row["email"].lower() for row in rows if row.get("email")}
    names = {row["name"] for row in rows if row.get("name")}
    users = User.objects.annotate(email_lower=Lower("email")).filter(
        Q(email_lower__in=emails) | Q(display_name__in=names)
    )

    by_email, by_name = {}, {}
    for user in users:
        by_email[user.email.lower()] = user
        if user.display_name:
            by_name.setdefault(user.display_name, []).append(user)
    return by_email, by_name


def _resolve(row, by_email, by_name):
    """The account this row would land on, matching the import's own rule.

    Email first; failing that, an unclaimed placeholder of the same name. A
    claimed account sharing the name is deliberately not a match — that is a
    conflict, not an answer.
    """
    email = (row.get("email") or "").lower()
    if email and (user := by_email.get(email)):
        return user
    for user in by_name.get(row.get("name"), []):
        if is_placeholder(user):
            return user
    return None


def find_name_conflicts(rows):
    """Rows whose name is already taken by a *claimed* account, with a different address.

    The import cannot decide these. "Jay Miller" in the export with a new work
    address might be the Jay Miller who already has an account, or a different
    Jay Miller entirely; guessing either way is wrong often enough to be worth
    a question. Placeholder-only matches are not conflicts — placeholders exist
    precisely to be claimed by name, and flagging every one of them would bury
    the real questions on a full re-upload.

    Returns a list of `{index, row, candidates, default}`, where `index` is the
    row's position in `rows` and `default` is what an unanswered import does.
    """
    by_email, by_name = _candidate_accounts(rows)

    conflicts = []
    for index, row in enumerate(rows):
        email = (row.get("email") or "").lower()
        if email and email in by_email:
            continue  # The address settles it.

        namesakes = by_name.get(row.get("name"), [])
        if not any(not is_placeholder(user) for user in namesakes):
            continue

        placeholder = next((user for user in namesakes if is_placeholder(user)), None)
        conflicts.append(
            {
                "index": index,
                "row": row,
                "candidates": namesakes,
                # Mirrors what get_or_create_supporter_user would do unasked.
                "default": f"link:{placeholder.pk}" if placeholder else "separate",
            }
        )
    return conflicts


def diff_roster(rows):
    """What importing `rows` would change, without writing anything.

    Returns `{added, unchanged, removed}` — `removed` being existing support
    records the file does not mention, which only actually go away on a
    `clear=True` import. Rows resolve to accounts through `_resolve`, the same
    rule the import follows, so the preview cannot promise something the import
    will not do. Counts assume the default answer to any name conflict.
    """
    from core.models import FoundationalSupport

    by_email, by_name = _candidate_accounts(rows)
    records = FoundationalSupport.objects.select_related("user")
    existing = {(support.user_id, support.year): support for support in records}

    added, unchanged, matched = [], [], set()
    for row in rows:
        user = _resolve(row, by_email, by_name)
        key = (user.pk, int(row["year"])) if user else None
        if key in existing:
            matched.add(key)
            unchanged.append(row)
        else:
            added.append(row)

    removed = [support for key, support in existing.items() if key not in matched]
    removed.sort(key=lambda support: (-support.year, support.display_name.lower()))
    return {"added": added, "unchanged": unchanged, "removed": removed}


@transaction.atomic
def import_supporters(rows, *, clear=False):
    """Load supporter records, optionally replacing the roster wholesale.

    `rows` are dicts of `name`, `email`, `year`, `status`. A row may also carry
    an answer to a name conflict (see `find_name_conflicts`): `user_id` pins it
    to a chosen account, leaving that account's own name and address untouched,
    and `separate` forces a fresh account rather than reusing a namesake's
    placeholder. Without either, matching is the usual email-then-placeholder.

    With `clear`, every
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
        if row.get("user_id"):
            user, created = User.objects.get(pk=row["user_id"]), False
        else:
            user, created = get_or_create_supporter_user(
                User,
                row.get("name", ""),
                row.get("email", ""),
                match_name=not row.get("separate"),
            )
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
