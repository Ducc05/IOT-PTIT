from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_user_profile_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="avatar",
            field=models.ImageField(blank=True, upload_to="avatars/%Y/%m/"),
        ),
    ]
