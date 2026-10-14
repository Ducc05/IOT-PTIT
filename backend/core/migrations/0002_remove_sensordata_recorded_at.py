from django.db import migrations, models


def preserve_received_at(apps, schema_editor):
    sensor_data = apps.get_model("core", "SensorData")
    sensor_data.objects.using(schema_editor.connection.alias).update(
        created_at=models.F("recorded_at")
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [
        migrations.RunPython(preserve_received_at, migrations.RunPython.noop),
        migrations.RemoveField(model_name="sensordata", name="recorded_at"),
    ]
