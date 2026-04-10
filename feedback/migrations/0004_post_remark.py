from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('feedback', '0003_favourite'),
    ]

    operations = [
        migrations.AddField(
            model_name='post',
            name='remark',
            field=models.TextField(blank=True, default=''),
        ),
    ]
