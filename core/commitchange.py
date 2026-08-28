"""Turn a CommitChange payments export into a foundational supporter roster.

CommitChange gives us one row per payment; what we keep is one record per
person per year, for anyone who gave at least the threshold ($200) in that
year. So the export has to be summed before it means anything — this module is
that step, and it hands `core.supporters.import_supporters` the `{name, email,
year}` rows it already knows how to load.

Anonymous payments are dropped rather than summed: a donor who asked not to be
named should not be pushed over the threshold by, or listed because of, a gift
they marked private. Someone whose *other* giving clears $200 on its own still
appears.

Column names are matched case-insensitively against the aliases below, since
the export's headers have moved around between CommitChange's own versions.
"""

import csv
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

DEFAULT_THRESHOLD = Decimal("200")

# First alias found in the header wins. `None` for EMAIL_COLUMNS' fallback:
# an export without an address still imports, just as placeholder accounts.
NAME_COLUMNS = ("full name", "name", "supporter name", "donor name", "supporter", "donor")
EMAIL_COLUMNS = ("email", "email address", "supporter email", "donor email")
DATE_COLUMNS = ("date", "payment date", "created at", "timestamp")
AMOUNT_COLUMNS = ("gross amount", "gross", "amount", "net amount")
ANONYMOUS_COLUMNS = ("anonymous?", "anonymous", "is anonymous")

TRUTHY = {"true", "t", "yes", "y", "1"}

DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y")


class CommitChangeError(ValueError):
    """The uploaded file is not a payments export we can read."""


def _find_column(fieldnames, aliases):
    """The header matching one of `aliases`, ignoring case and stray spaces."""
    lookup = {(name or "").strip().lower(): name for name in fieldnames}
    for alias in aliases:
        if alias in lookup:
            return lookup[alias]
    return None


def _parse_amount(value):
    """`"$1,234.50"` → `Decimal("1234.50")`; parenthesised values are refunds."""
    text = (value or "").strip()
    if not text:
        return Decimal("0")

    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace("$", "").replace(",", "").replace(" ", "")
    if text.startswith("-"):
        negative, text = True, text[1:]

    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise CommitChangeError(f"Could not read {value!r} as an amount.") from exc
    return -amount if negative else amount


def _parse_year(value):
    text = (value or "").strip()
    if not text:
        raise CommitChangeError("A payment row has no date.")

    # ISO first, including the timestamped variants the API export uses.
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).year
    except ValueError:
        pass

    head = text.split(" ")[0].split("T")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(head, fmt).year
        except ValueError:
            continue
    raise CommitChangeError(f"Could not read {value!r} as a date.")


def _is_anonymous(value):
    return (value or "").strip().lower() in TRUTHY


def _tidy_name(name):
    """Fix shouted or lowercased entries, but leave deliberate casing alone.

    Title-casing everything would turn "Jay McDonald" into "Jay Mcdonald", so
    a name that already mixes cases is taken as typed.
    """
    return name.title() if name.isupper() or name.islower() else name


def aggregate_payments(text, *, threshold=DEFAULT_THRESHOLD):
    """Sum a payments export into roster rows, one per supporter per year.

    Returns `(rows, summary)`. Each row is `{name, email, year, total}` —
    `import_supporters` reads the first three and ignores `total`, which is
    there so the preview can show what earned someone their place.

    People are keyed on their email where the export has one, so a supporter
    who changed the spelling of their name between gifts still totals as one
    person. Only rows without an address fall back to keying on the name.
    """
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise CommitChangeError("The file is empty.")

    name_col = _find_column(reader.fieldnames, NAME_COLUMNS)
    date_col = _find_column(reader.fieldnames, DATE_COLUMNS)
    amount_col = _find_column(reader.fieldnames, AMOUNT_COLUMNS)
    email_col = _find_column(reader.fieldnames, EMAIL_COLUMNS)
    anon_col = _find_column(reader.fieldnames, ANONYMOUS_COLUMNS)

    missing = [
        label
        for label, column in (("a name", name_col), ("a date", date_col), ("an amount", amount_col))
        if column is None
    ]
    if missing:
        found = ", ".join(reader.fieldnames)
        raise CommitChangeError(f"The export needs {' and '.join(missing)} column. Found: {found}")

    totals = defaultdict(Decimal)
    names = {}
    emails = {}
    counts = {"rows": 0, "anonymous": 0, "unnamed": 0}

    for record in reader:
        counts["rows"] += 1

        if anon_col and _is_anonymous(record.get(anon_col)):
            counts["anonymous"] += 1
            continue

        name = (record.get(name_col) or "").strip()
        email = (record.get(email_col) or "").strip() if email_col else ""
        if not name and not email:
            counts["unnamed"] += 1
            continue

        year = _parse_year(record.get(date_col))
        key = (email.lower() or name.lower(), year)

        totals[key] += _parse_amount(record.get(amount_col))
        # Latest spelling and address win, so a corrected record supersedes.
        if name:
            names[key] = name
        if email:
            emails[key] = email

    rows = [
        {
            "name": _tidy_name(names.get(key, "")),
            "email": emails.get(key, ""),
            "year": str(key[1]),
            "total": total,
        }
        for key, total in totals.items()
        if total >= threshold
    ]
    rows.sort(key=lambda row: (-int(row["year"]), row["name"].lower()))

    summary = {
        "payments": counts["rows"],
        "anonymous_skipped": counts["anonymous"],
        "unnamed_skipped": counts["unnamed"],
        "below_threshold": len(totals) - len(rows),
        "supporters": len(rows),
        "years": sorted({row["year"] for row in rows}, reverse=True),
        "has_email_column": email_col is not None,
        "has_anonymous_column": anon_col is not None,
    }
    return rows, summary
