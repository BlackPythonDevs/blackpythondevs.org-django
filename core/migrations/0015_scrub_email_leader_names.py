from django.db import migrations


def scrub_email_names(apps, schema_editor):
    """Auto-created roster entries used the user's email as their public name.

    Rename them to the user's display name; if there isn't one, drop the
    auto-created entry rather than keep listing an email on the About page.
    """
    Leader = apps.get_model("core", "Leader")
    for leader in Leader.objects.filter(name__contains="@").select_related("user"):
        user = leader.user
        if user and user.display_name:
            leader.name = user.display_name
            leader.save(update_fields=["name"])
        elif user and leader.name == user.email:
            leader.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0014_remove_sponsor_tier"),
        ("users", "0008_user_state_province"),
    ]

    operations = [migrations.RunPython(scrub_email_names, migrations.RunPython.noop)]
