from django.apps import AppConfig


class CocReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "coc_reports"
    verbose_name = "Code of Conduct reports"

    def ready(self):
        # Registered here (rather than in checklists) because checklists is
        # a generic app that never imports the models it tracks — see
        # checklists/registry.py.
        #
        # The four steps are the CoC Action Policy's own sequence: confirm
        # receipt, discuss, conclude, then tell the reporter. view_permission
        # and detail_template close the checklists console for this model —
        # anyone without the COC Report Viewing role can't list or open these
        # checklists there, and the console renders no report text even for
        # those who can (see coc_reports/models.CocReport and
        # checklists/views.py).
        from checklists.registry import register

        from .models import CocReport

        register(
            CocReport,
            [
                "CoC has made initial confirmation of response",
                "CoC has discussed",
                "Conclusion has been found",
                "Reporter has been notified",
            ],
            name="Code of Conduct report",
            view_permission="coc_reports.view_cocreport",
            detail_template="coc_reports/checklist_detail.html",
        )
