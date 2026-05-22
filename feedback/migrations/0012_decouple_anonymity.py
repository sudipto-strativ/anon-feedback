"""Decouple Post/Comment from User to make anonymous feedback truly anonymous.

What this migration does, in order:

1. Adds `Post.public_id` (UUIDField, nullable for now so we can backfill).
2. Adds `Comment.role` (CharField snapshot, default 'employee').
3. Creates the `Subscription` table — interest graph that replaces the
   author FK as the routing mechanism for in-app notifications.
4. Runs a Python data step that:
   - Fills each Post's `public_id` with a fresh uuid4().
   - Copies each Comment's author's profile role into `Comment.role`
     (snapshot of the role at the moment of speaking — see model docstring).
   - Creates Subscription rows: one per Post.author, one per Comment.author,
     one per Favourite.user. After this step we have enough subscribers on
     every existing post for notifications to continue working.
5. Tightens `Post.public_id` to NOT NULL + unique=True.
6. Drops `Post.author` and `Comment.author` FK columns.

This migration is destructive by design: step 6 destroys the only
authoritative source of authorship in the database. Reverse direction is
NoOp; you cannot recover authorship after this runs. Take a database
snapshot before applying.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _backfill(apps, schema_editor):
    Post = apps.get_model('feedback', 'Post')
    Comment = apps.get_model('feedback', 'Comment')
    Favourite = apps.get_model('feedback', 'Favourite')
    Subscription = apps.get_model('feedback', 'Subscription')
    UserProfile = apps.get_model('feedback', 'UserProfile')

    # 1. Backfill Post.public_id with a fresh UUID per row.
    for post in Post.objects.all():
        post.public_id = uuid.uuid4()
        post.save(update_fields=['public_id'])

    # 2. Backfill Comment.role from the old author FK.
    #    Use the historical model to look up the profile.
    profile_role_by_user_id = {
        p.user_id: p.role
        for p in UserProfile.objects.all()
    }
    for comment in Comment.objects.all():
        comment.role = profile_role_by_user_id.get(comment.author_id, 'employee')
        comment.save(update_fields=['role'])

    # 3. Backfill Subscription rows.
    #    - One per Post.author (the original poster auto-subscribes).
    #    - One per Comment.author (commenters auto-subscribe).
    #    - One per Favourite.user (bookmarkers auto-subscribe).
    #    Dedup via a set keyed on (user_id, post_id).
    pairs = set()
    for p in Post.objects.all():
        pairs.add((p.author_id, p.id))
    for c in Comment.objects.all():
        pairs.add((c.author_id, c.post_id))
    for f in Favourite.objects.all():
        pairs.add((f.user_id, f.post_id))

    Subscription.objects.bulk_create(
        [
            Subscription(user_id=uid, post_id=pid)
            for (uid, pid) in pairs
        ],
        ignore_conflicts=True,
    )


def _forward_only(apps, schema_editor):
    # This migration is destructive in the forward direction. Recovering
    # authorship after the FK is dropped is impossible by design.
    raise RuntimeError(
        "0012_decouple_anonymity is not reversible — authorship is dropped "
        "intentionally as part of the anonymity hardening. If you need to "
        "go back, restore from the snapshot taken before this migration ran."
    )


class Migration(migrations.Migration):

    dependencies = [
        ('feedback', '0011_notification_type'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Step 1 — add new fields (nullable + defaults so existing rows
        # remain valid before backfill).
        migrations.AddField(
            model_name='post',
            name='public_id',
            field=models.UUIDField(default=uuid.uuid4, null=True, editable=False),
        ),
        migrations.AddField(
            model_name='comment',
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
                help_text='Snapshot of commenter role at post time. No user FK is stored.',
            ),
        ),
        # Step 2 — Subscription table (interest graph).
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'post',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='subscribers',
                        to='feedback.post',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='subscriptions',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name='subscription',
            constraint=models.UniqueConstraint(fields=('user', 'post'), name='unique_subscription'),
        ),
        migrations.AddIndex(
            model_name='subscription',
            index=models.Index(fields=['post'], name='feedback_su_post_id_13446e_idx'),
        ),

        # Step 3 — backfill while old author FKs are still around.
        migrations.RunPython(_backfill, reverse_code=_forward_only),

        # Step 4 — tighten public_id to NOT NULL + unique.
        migrations.AlterField(
            model_name='post',
            name='public_id',
            field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
        ),

        # Step 5 — destroy the author link forever.
        migrations.RemoveField(model_name='post', name='author'),
        migrations.RemoveField(model_name='comment', name='author'),
    ]
