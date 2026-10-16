from django.db import migrations, models


def fill_names(apps, schema_editor):
    AuditEntry = apps.get_model("audit", "AuditEntry")
    for entry in AuditEntry.objects.filter(championship__isnull=False).select_related("championship"):
        entry.championship_name = entry.championship.name
        entry.save(update_fields=["championship_name"])


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="auditentry",
            name="championship_name",
            field=models.CharField(blank=True, default="", max_length=100),
            preserve_default=False,
        ),
        migrations.RunPython(fill_names, migrations.RunPython.noop),
    ]
