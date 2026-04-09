import django.db.models.deletion
import django.db.models.expressions
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationEmail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='SlackConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('webhook_url', models.URLField()),
                ('channel_name', models.CharField(blank=True, max_length=100)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Slack Configuration',
            },
        ),
        migrations.CreateModel(
            name='Post',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField()),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('in_progress', 'In Progress'),
                        ('done', 'Done'),
                        ('rejected', 'Rejected'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('eta', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('author', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='posts',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('status_updated_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='status_updates',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(
                    choices=[
                        ('employee', 'Employee'),
                        ('hr', 'HR'),
                        ('ceo', 'CEO'),
                    ],
                    default='employee',
                    max_length=20,
                )),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='profile',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.CreateModel(
            name='Comment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('author', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='comments',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('post', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='comments',
                    to='feedback.post',
                )),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
        migrations.CreateModel(
            name='Vote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vote_type', models.CharField(choices=[('like', 'Like'), ('dislike', 'Dislike')], max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('comment', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='votes',
                    to='feedback.comment',
                )),
                ('post', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='votes',
                    to='feedback.post',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='votes',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.AddConstraint(
            model_name='vote',
            constraint=models.UniqueConstraint(
                condition=models.Q(post__isnull=False),
                fields=['user', 'post'],
                name='unique_post_vote',
            ),
        ),
        migrations.AddConstraint(
            model_name='vote',
            constraint=models.UniqueConstraint(
                condition=models.Q(comment__isnull=False),
                fields=['user', 'comment'],
                name='unique_comment_vote',
            ),
        ),
    ]
