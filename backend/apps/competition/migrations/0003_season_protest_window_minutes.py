from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("competition", "0002_session_attempt_session_unique_session_kind_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="season",
            name="protest_window_minutes",
            field=models.PositiveIntegerField(default=60),
        ),
    ]
