import os
import uuid

from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('employee', 'Member'),
        ('hr', 'HR'),
        ('ceo', 'CEO'),
        ('admin', 'Admin'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def role_display(self):
        return dict(self.ROLE_CHOICES).get(self.role, 'Member')


class NotificationEmail(models.Model):
    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=20, null=True, blank=True,
        choices=UserProfile.ROLE_CHOICES,
        help_text='If set, only notified for posts targeted at this role. Leave blank for public post notifications.',
    )
    notify_on_new_post = models.BooleanField(default=True)
    notify_on_new_comment = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        role_label = f' [{self.get_role_display()}]' if self.role else ''
        return f"{self.email}{role_label}"


class SlackConfig(models.Model):
    webhook_url = models.URLField()
    channel_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Slack Configuration"

    def __str__(self):
        return f"Slack: {self.channel_name or self.webhook_url}"


class Post(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('rejected', 'Rejected'),
    ]
    # No author FK — this is the structural change that makes "anonymous"
    # actually anonymous at the database layer. Authorship is no longer
    # stored. Notification routing happens via the Subscription model, which
    # is an interest graph (many subscribers per post), not an ownership
    # link. See docs in feedback/models.py:Subscription.
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    content = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    target_role = models.CharField(
        max_length=20, null=True, blank=True,
        choices=UserProfile.ROLE_CHOICES,
        help_text='If set, only the author and users with this role can see this post.',
    )
    eta = models.DateField(null=True, blank=True)
    status_updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='status_updates'
    )
    remark = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Post #{self.id} at {self.created_at:%Y-%m-%d}"

    @property
    def like_count(self):
        return self.votes.filter(vote_type='like').count()

    @property
    def dislike_count(self):
        return self.votes.filter(vote_type='dislike').count()

    @property
    def score(self):
        return self.like_count - self.dislike_count

    @property
    def comment_count(self):
        return self.comments.count()

    def get_status_color(self):
        colors = {
            'pending': 'warning',
            'in_progress': 'primary',
            'done': 'success',
            'rejected': 'danger',
        }
        return colors.get(self.status, 'secondary')


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    # No author FK. The role at the time of commenting is captured as a snapshot
    # so templates and Slack can show "HR commented" / "CEO commented" without
    # storing who. If a user changes role later, old comments keep their
    # original role label — intentional, that's the role at the moment of
    # speaking.
    role = models.CharField(
        max_length=20,
        choices=UserProfile.ROLE_CHOICES,
        default='employee',
        help_text='Snapshot of commenter role at post time. No user FK is stored.',
    )
    content = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment #{self.id} on Post #{self.post.id}"

    @property
    def role_display(self):
        return dict(UserProfile.ROLE_CHOICES).get(self.role, 'Member')

    @property
    def like_count(self):
        return self.votes.filter(vote_type='like').count()

    @property
    def dislike_count(self):
        return self.votes.filter(vote_type='dislike').count()

    @property
    def score(self):
        return self.like_count - self.dislike_count


class Favourite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favourites')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='favourited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'post'], name='unique_favourite')
        ]

    def __str__(self):
        return f"{self.user.username} → Post #{self.post.id}"


class Subscription(models.Model):
    """Interest graph for notifications, replacing the dropped Post/Comment
    author FK as the routing mechanism.

    A row says "this user wants notifications about this post." A user
    auto-subscribes when they create a post, comment, or favourite it. The
    first subscriber on a freshly-created post will usually be the author,
    so this table still leaks a *soft* authorship signal — but it's an
    interest signal (many users can subscribe to the same post), not the
    deterministic key the old FK was.

    No `created_at` field on purpose: ordering by creation would re-leak
    the authorship signal we just dropped. Rows are unordered facts.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='subscribers')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'post'], name='unique_subscription'),
        ]
        indexes = [models.Index(fields=['post'])]

    def __str__(self):
        return f"sub: user={self.user_id} post={self.post_id}"


class PostAttachment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='post_attachments/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for Post #{self.post_id}: {self.filename}"

    @property
    def filename(self):
        return os.path.basename(self.file.name)

    @property
    def display_name(self):
        """Neutral label shown in templates.

        Stored filenames are random tokens (see `utils/uploads.py`), so
        showing them in the UI would expose nothing identifying — but a
        clean "attachment.pdf" reads better and avoids confusing
        readers with opaque base64-ish strings.
        """
        return f"attachment{self.extension}"

    @property
    def extension(self):
        return os.path.splitext(self.file.name)[1].lower()

    @property
    def is_image(self):
        return self.extension in ('.jpg', '.jpeg', '.png', '.gif', '.webp')

    @property
    def icon_class(self):
        return {
            '.pdf': 'bi-file-pdf-fill',
            '.doc': 'bi-file-word-fill', '.docx': 'bi-file-word-fill',
            '.xls': 'bi-file-excel-fill', '.xlsx': 'bi-file-excel-fill',
            '.csv': 'bi-file-spreadsheet-fill',
        }.get(self.extension, 'bi-file-earmark-fill')

    @property
    def icon_color(self):
        return {
            '.pdf': '#ef4444',
            '.doc': '#2563eb', '.docx': '#2563eb',
            '.xls': '#16a34a', '.xlsx': '#16a34a', '.csv': '#16a34a',
        }.get(self.extension, '#6366f1')


class CommentImage(models.Model):
    comment = models.ForeignKey('Comment', on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='comment_images/%Y/%m/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for Comment #{self.comment_id}"


class Notification(models.Model):
    TYPE_COMMENT = 'comment'
    TYPE_STATUS = 'status_update'
    TYPE_CHOICES = [
        (TYPE_COMMENT, 'Comment'),
        (TYPE_STATUS, 'Status Update'),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_COMMENT)
    comment = models.ForeignKey(
        'Comment', on_delete=models.CASCADE, related_name='notifications',
        null=True, blank=True,
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f"Notification for {self.recipient.username} → Post #{self.post_id}"


class Vote(models.Model):
    VOTE_CHOICES = [('like', 'Like'), ('dislike', 'Dislike')]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='votes')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='votes', null=True, blank=True)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name='votes', null=True, blank=True)
    vote_type = models.CharField(max_length=10, choices=VOTE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'post'],
                condition=models.Q(post__isnull=False),
                name='unique_post_vote'
            ),
            models.UniqueConstraint(
                fields=['user', 'comment'],
                condition=models.Q(comment__isnull=False),
                name='unique_comment_vote'
            ),
        ]
