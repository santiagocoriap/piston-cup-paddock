from django.db import migrations, models


def fill_country(apps, schema_editor):
    """A track gets the country of its first layout that has one."""
    Track = apps.get_model("catalog", "Track")
    for track in Track.objects.all():
        layout = track.layouts.exclude(country="").order_by("id").first()
        if layout:
            track.country = layout.country
            track.save(update_fields=["country"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0005_game_images")]

    operations = [
        migrations.AddField(
            model_name="track",
            name="country",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.RunPython(fill_country, migrations.RunPython.noop),
    ]
