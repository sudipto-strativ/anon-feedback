from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('feedback', '0007_alter_userprofile_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                choices=[
                    ('employee', 'Member'),
                    ('hr', 'HR'),
                    ('ceo', 'CEO'),
                    ('admin', 'Admin'),
                ],
                default='employee',
                max_length=20,
            ),
        ),
    ]
