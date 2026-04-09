from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('feedback', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificationemail',
            name='notify_on_new_post',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='notificationemail',
            name='notify_on_new_comment',
            field=models.BooleanField(default=True),
        ),
    ]
