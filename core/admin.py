"""Django admin for foundational support, including the CommitChange import.

The roster itself is normally edited as a Wagtail snippet; what lives here is
the once-a-year job that snippet editing is bad at — dropping in the payments
export from CommitChange and letting the site work out who cleared $200.

The import is two steps on purpose. Uploading only parses and compares, and
the parsed roster is held in the session until the second POST confirms it, so
a mis-shaped export or an unexpected `--replace`-style wipe is something you
see before it happens rather than after.
"""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from core.commitchange import DEFAULT_THRESHOLD, CommitChangeError, aggregate_payments
from core.models import FoundationalSupport
from core.supporters import diff_roster, find_name_conflicts, import_supporters, is_placeholder

SESSION_KEY = "commitchange_import"


class CommitChangeImportForm(forms.Form):
    csv_file = forms.FileField(
        label="CommitChange payments export",
        help_text="The payments CSV, with its Date, Full Name and Gross Amount columns.",
    )
    threshold = forms.DecimalField(
        label="Minimum given per year",
        initial=DEFAULT_THRESHOLD,
        min_value=0,
        decimal_places=2,
        help_text="Someone is a foundational supporter for a year once their non-anonymous giving reaches this.",
    )
    replace = forms.BooleanField(
        label="Replace the whole roster",
        required=False,
        help_text=(
            "Treat the export as the complete history: support records it does not mention are deleted, "
            "along with any placeholder accounts left with nothing. Leave off to only add and update."
        ),
    )

    def clean_csv_file(self):
        upload = self.cleaned_data["csv_file"]
        try:
            return upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise forms.ValidationError("That file is not UTF-8 text — export it again as CSV.") from None


@admin.register(FoundationalSupport)
class FoundationalSupportAdmin(admin.ModelAdmin):
    list_display = ("display_name", "year", "status", "note")
    list_filter = ("status", "year")
    search_fields = ("user__display_name", "user__email", "note")
    autocomplete_fields = ("user",)
    ordering = ("-year",)
    list_select_related = ("user",)
    change_list_template = "admin/core/foundationalsupport/change_list.html"

    @admin.display(description="Supporter", ordering="user__display_name")
    def display_name(self, obj):
        return obj.display_name

    def get_urls(self):
        own = [
            path(
                "import-commitchange/",
                self.admin_site.admin_view(self.import_commitchange),
                name="core_foundationalsupport_import",
            ),
        ]
        return own + super().get_urls()

    def import_commitchange(self, request):
        """Upload and preview on the first POST; write on the confirming one."""
        # `admin_view` only asks for staff; importing writes the roster.
        if not (self.has_add_permission(request) and self.has_change_permission(request)):
            raise PermissionDenied

        if request.method == "POST" and "confirm" in request.POST:
            return self._apply(request)

        form = CommitChangeImportForm(request.POST or None, request.FILES or None)
        context = {
            **self.admin_site.each_context(request),
            "title": "Import CommitChange payments",
            "opts": self.model._meta,
            "form": form,
        }

        if request.method == "POST" and form.is_valid():
            try:
                rows, summary = aggregate_payments(
                    form.cleaned_data["csv_file"],
                    threshold=form.cleaned_data["threshold"],
                )
            except CommitChangeError as error:
                form.add_error("csv_file", str(error))
            else:
                if not rows:
                    form.add_error("csv_file", "No one in that export reached the threshold.")
                else:
                    return self._preview(request, rows, summary, replace=form.cleaned_data["replace"])

        return TemplateResponse(request, "admin/core/foundationalsupport/import.html", context)

    def _preview(self, request, rows, summary, *, replace):
        """Stash the parsed roster and show what applying it would do."""
        diff = diff_roster(rows)
        conflicts = find_name_conflicts(rows)
        # Decimals do not survive the session's JSON encoding, and the import
        # itself has no use for them — the totals are for the eye only. The
        # accounts each conflict may be answered with are stashed too, so the
        # confirming POST can only pick from what was actually offered.
        request.session[SESSION_KEY] = {
            "rows": [{key: str(value) for key, value in row.items()} for row in rows],
            "replace": replace,
            "choices": {str(conflict["index"]): [user.pk for user in conflict["candidates"]] for conflict in conflicts},
        }

        by_year = {}
        for row in rows:
            by_year.setdefault(row["year"], []).append(row)

        context = {
            **self.admin_site.each_context(request),
            "title": "Confirm CommitChange import",
            "opts": self.model._meta,
            "summary": summary,
            "replace": replace,
            "added": diff["added"],
            "unchanged": diff["unchanged"],
            "removed": diff["removed"],
            "without_email": [row for row in rows if not row["email"]],
            "by_year": sorted(by_year.items(), reverse=True),
            "conflicts": [self._conflict_context(conflict) for conflict in conflicts],
        }
        return TemplateResponse(request, "admin/core/foundationalsupport/preview.html", context)

    def _conflict_context(self, conflict):
        """One name clash, phrased as a question with its possible answers."""
        options = [
            {
                "value": f"link:{user.pk}",
                "label": f"Same person as {user.display_name or user}",
                "detail": (
                    "an unclaimed placeholder — its address will become the one in the export"
                    if is_placeholder(user)
                    else f"already signed up as {user.email}; their address is left as it is"
                ),
                "checked": conflict["default"] == f"link:{user.pk}",
            }
            for user in conflict["candidates"]
        ]
        options.append(
            {
                "value": "separate",
                "label": "A different person of the same name",
                "detail": "gets their own account, and will be listed separately",
                "checked": conflict["default"] == "separate",
            }
        )
        options.append(
            {
                "value": "skip",
                "label": "Leave this one out",
                "detail": "nothing is recorded for them this time",
                "checked": False,
            }
        )
        return {"index": conflict["index"], "row": conflict["row"], "options": options}

    def _resolve_rows(self, stashed, posted):
        """Apply the answers on the confirm form to the stashed roster."""
        rows = []
        for index, row in enumerate(stashed["rows"]):
            allowed = stashed.get("choices", {}).get(str(index))
            if not allowed:
                rows.append(row)
                continue

            choice = posted.get(f"resolve_{index}", "")
            if choice == "skip":
                continue
            if choice == "separate":
                rows.append({**row, "separate": True})
                continue
            if choice.startswith("link:") and choice.removeprefix("link:").isdigit():
                # Only an account this very preview offered, so a hand-edited
                # form cannot attach support to some unrelated member.
                pk = int(choice.removeprefix("link:"))
                if pk in allowed:
                    rows.append({**row, "user_id": pk})
                    continue
            rows.append(row)
        return rows

    def _apply(self, request):
        stashed = request.session.pop(SESSION_KEY, None)
        if not stashed:
            self.message_user(
                request,
                "That preview has expired — upload the export again.",
                level=messages.WARNING,
            )
            return redirect("admin:core_foundationalsupport_import")

        rows = self._resolve_rows(stashed, request.POST)
        skipped = len(stashed["rows"]) - len(rows)
        stats = import_supporters(rows, clear=stashed["replace"])
        note = (
            f"Imported {stats['support']} support records, creating {stats['users_created']} accounts."
            if not stashed["replace"]
            else (
                f"Replaced the roster: cleared {stats['support_deleted']} records and "
                f"{stats['users_deleted']} unclaimed placeholder accounts, then imported "
                f"{stats['support']} records, creating {stats['users_created']} accounts."
            )
        )
        if skipped:
            note += f" {skipped} row{'' if skipped == 1 else 's'} left out at your request."
        self.message_user(request, note, level=messages.SUCCESS)
        return redirect(reverse("admin:core_foundationalsupport_changelist"))
