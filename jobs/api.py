"""Key-authenticated JSON write API for jobs (issue #225).

External systems (an Ashby/Greenhouse/Rippling-style push, a sponsor's own
cron job) create and update postings here. Two rules dominate the design:

* **Authentication is project-issued.** The only credential handled is our own
  ``JobAPIKey`` (see ``jobs.models``); a third-party recruiting-platform
  credential is never accepted, stored, or proxied. A missing, unknown,
  inactive, expired, or revoked key all return the *same* 401 body, so the
  response never reveals whether a key or a job exists.
* **No mass assignment.** The owning sponsor comes from the key, never the
  body; the writable field set is an explicit allowlist and any unrecognized
  field is a 400. ``status``/``is_published``/``source``/``external_id`` and
  friends are simply not writable here.

Plain Django ``JsonResponse`` — no DRF, so no new dependency, no browsable API,
and no session-auth/CSRF interaction to reason about.
"""

import json

from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Job, parse_api_key

# Body fields a caller may write. Everything else is rejected. Deliberately
# excludes sponsor, id, status, is_published, published_at, source,
# external_id, created_at and updated_at — the key's sponsor and the model
# defaults own those.
WRITABLE_FIELDS = (
    "title",
    "description",
    "apply_url",
    "location",
    "remote",
    "employment_type",
)

# Bounds for the free-text fields. `title`/`location` match the model's
# max_length; `description` is a TextField, so cap it explicitly rather than
# letting a caller store an unbounded blob.
TITLE_MAX = 200
LOCATION_MAX = 200
DESCRIPTION_MAX = 20000

# Field name -> public JSON name. `sponsor` is the sponsor's name, never its id
# or any internal column.
RESPONSE_FIELDS = (
    "id",
    "title",
    "description",
    "apply_url",
    "location",
    "remote",
    "employment_type",
    "published_at",
)

# HTTP status for every authentication failure. Identical body and status for
# unknown key, bad secret, inactive, expired, revoked, and missing header.
_UNAUTHENTICATED = (401, {"detail": "Invalid or missing API key."})


def _error(status, message, field=None):
    body = {"detail": message}
    if field is not None:
        body["field"] = field
    return JsonResponse(body, status=status)


def _presented_key(request):
    """Pull the key out of the Authorization or X-API-Key header, if any."""
    header = request.headers.get("Authorization", "")
    if header:
        scheme, _, value = header.partition(" ")
        if scheme.lower() in ("bearer", "token", "apikey") and value:
            return value.strip()
        # A bare Authorization value (no scheme) is accepted too.
        return header.strip()
    return request.headers.get("X-API-Key", "").strip() or None


# A hash of a throwaway value, used as the comparison target when no key row
# matches so the miss path runs the same `check_password` work as a hit. Its
# only purpose is to keep unknown-key and wrong-secret responses the same cost.
_DUMMY_HASH = make_password("jeremy-the-vole")


def _authenticate(request):
    """Return the matching active JobAPIKey, or None.

    Lookup is by the non-secret ``key_id`` (one indexed row), then the secret
    is checked with ``check_password``. The whole-key loop/compare alternative
    is never used, and a missing row still runs one ``check_password`` so the
    response time does not reveal whether the key id exists.
    """
    from .models import JobAPIKey

    presented = _presented_key(request)
    if not presented:
        return None
    parsed = parse_api_key(presented)
    if parsed is None:
        return None
    key_id, secret = parsed
    key = JobAPIKey.objects.filter(key_id=key_id).select_related("sponsor").first()
    # Always run check_password (against the dummy hash when there is no row),
    # then gate on the row's active/expiry state — same cost, same body, for
    # unknown, inactive, expired and revoked keys.
    verified = check_password(secret, key.key_hash if key is not None else _DUMMY_HASH)
    if key is None or not verified:
        return None
    if not key.is_active():
        return None
    return key


def _read_body(request):
    """Parse the request body as a JSON object, or return ``(None, error)."""
    if not request.body:
        return {}, None
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return None, _error(400, "Request body must be valid JSON.")
    if not isinstance(data, dict):
        return None, _error(400, "Request body must be a JSON object.")
    return data, None


def _clean_fields(data, *, partial):
    """Validate a body against the writable allowlist.

    Returns ``(cleaned, error)`` where ``cleaned`` holds only model field
    names ready to assign. Unknown fields, wrong types, out-of-range values and
    invalid choices are all 400s.
    """
    unknown = sorted(set(data) - set(WRITABLE_FIELDS))
    if unknown:
        return None, _error(400, f"Unrecognized field(s): {', '.join(unknown)}.")

    cleaned = {}

    if "title" in data:
        title = data["title"]
        if not isinstance(title, str) or not title.strip():
            return None, _error(400, "title must be a non-empty string.", "title")
        if len(title) > TITLE_MAX:
            return None, _error(400, f"title must be at most {TITLE_MAX} characters.", "title")
        cleaned["title"] = title.strip()
    elif not partial:
        return None, _error(400, "title is required.", "title")

    if "description" in data:
        description = data["description"]
        if not isinstance(description, str):
            return None, _error(400, "description must be a string.", "description")
        if len(description) > DESCRIPTION_MAX:
            return None, _error(400, f"description must be at most {DESCRIPTION_MAX} characters.", "description")
        cleaned["description"] = description

    if "location" in data:
        location = data["location"]
        if not isinstance(location, str):
            return None, _error(400, "location must be a string.", "location")
        if len(location) > LOCATION_MAX:
            return None, _error(400, f"location must be at most {LOCATION_MAX} characters.", "location")
        cleaned["location"] = location.strip()

    if "remote" in data:
        remote = data["remote"]
        if not isinstance(remote, bool):
            return None, _error(400, "remote must be a boolean.", "remote")
        cleaned["remote"] = remote

    if "employment_type" in data:
        employment_type = data["employment_type"]
        valid = {choice for choice, _ in Job.EMPLOYMENT_TYPE_CHOICES}
        if not isinstance(employment_type, str) or employment_type not in valid:
            return None, _error(
                400,
                f"employment_type must be one of: {', '.join(sorted(valid))}.",
                "employment_type",
            )
        cleaned["employment_type"] = employment_type

    if "apply_url" in data:
        apply_url = data["apply_url"]
        if not isinstance(apply_url, str) or not apply_url.strip():
            return None, _error(400, "apply_url must be a non-empty string.", "apply_url")
        validator = Job._meta.get_field("apply_url").validators[0]
        try:
            validator(apply_url)
        except ValidationError:
            return None, _error(400, "apply_url must be a valid http(s) URL.", "apply_url")
        cleaned["apply_url"] = apply_url
    elif not partial:
        return None, _error(400, "apply_url is required.", "apply_url")

    return cleaned, None


def _serialize(job):
    """Public JSON for a job written through the API.

    Only public fields plus the sponsor's display name. Internal bookkeeping
    (status, source, external_id, timestamps) never leaves the server.
    """
    data = {field: getattr(job, field) for field in RESPONSE_FIELDS}
    if data["published_at"] is not None:
        data["published_at"] = data["published_at"].isoformat()
    data["sponsor"] = job.sponsor.name
    data["employment_type_display"] = job.get_employment_type_display()
    return data


@csrf_exempt
@require_http_methods(["POST", "PUT"])
def job_api(request, pk=None):
    """Create (POST /jobs/api/jobs/) or update (PUT /jobs/api/jobs/<pk>/) a job.

    Auth runs first and short-circuits identically for every failure, so an
    unauthenticated caller learns nothing about which jobs exist.
    """
    key = _authenticate(request)
    if key is None:
        status, body = _UNAUTHENTICATED
        return JsonResponse(body, status=status)

    data, error = _read_body(request)
    if error is not None:
        return error

    if request.method == "POST":
        cleaned, error = _clean_fields(data, partial=False)
        if error is not None:
            return error
        job = Job(sponsor=key.sponsor, **cleaned)
        job.full_clean(exclude=["sponsor"], validate_unique=False)
        job.save()
        key.touch()
        return JsonResponse(_serialize(job), status=201)

    # PUT: the job must exist *within the key's sponsor scope*, else 404. This
    # is checked after auth, so an unauthenticated probe still only sees 401.
    job = Job.objects.filter(pk=pk, sponsor=key.sponsor).select_related("sponsor").first()
    if job is None:
        return _error(404, "Job not found.")
    cleaned, error = _clean_fields(data, partial=True)
    if error is not None:
        return error
    for field, value in cleaned.items():
        setattr(job, field, value)
    job.full_clean(exclude=["sponsor"], validate_unique=False)
    job.save()
    key.touch()
    return JsonResponse(_serialize(job))
