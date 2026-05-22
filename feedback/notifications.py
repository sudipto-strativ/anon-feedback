"""Strativ Voice notifications.

This module fans out to three channels: Slack (webhook), email
(`NotificationEmail` admin list), and in-app `Notification` rows.

After the anonymity hardening:

- Slack messages no longer carry a role badge for comments
  (`HR / CEO / Admin / Member`). With rare roles, that badge was an
  instant deanonymiser.
- URLs in Slack and email subject lines use `post.public_id` (UUID),
  not the sequential `post.id` — so externally we can't enumerate.
- In-app notifications are routed via `Subscription` instead of the
  dropped `Post.author` / `Comment.author` FKs. Anyone who has shown
  interest in a post (created it, commented on it, favourited it) gets
  notified about subsequent activity.
"""

import logging

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from .models import Notification, NotificationEmail, SlackConfig, Subscription

logger = logging.getLogger(__name__)


def send_slack_message(text):
    """Send a message to Slack via webhook."""
    config = SlackConfig.objects.filter(is_active=True).first()
    if not config:
        webhook_url = getattr(settings, 'SLACK_WEBHOOK_URL', '')
        if not webhook_url:
            return
        try:
            requests.post(webhook_url, json={"text": text}, timeout=5)
        except Exception as e:
            logger.error(f"Slack notification failed: {e}")
        return

    try:
        payload = {"text": text}
        if config.channel_name:
            payload["channel"] = config.channel_name
        requests.post(config.webhook_url, json=payload, timeout=5)
    except Exception as e:
        logger.error(f"Slack notification failed: {e}")


def _post_url(post):
    """Absolute URL for a post detail page, routed by public_id (UUID)."""
    site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').rstrip('/')
    return site_url + reverse('post_detail', args=[post.public_id])


def notify_new_post(post):
    """Notify admins about a new post via Slack (public only) and email."""
    url = _post_url(post)

    if not post.target_role:
        msg = (
            f":mega: *<{url}|New Feedback Posted>*\n"
            f">{post.content[:200]}"
        )
        send_slack_message(msg)

    if not getattr(settings, 'EMAIL_NOTIFICATION_ENABLED', True):
        return

    email_qs = NotificationEmail.objects.filter(notify_on_new_post=True)
    if post.target_role:
        email_qs = email_qs.filter(role=post.target_role)
    else:
        email_qs = email_qs.filter(role__isnull=True)

    emails = list(email_qs.values_list('email', flat=True))
    if emails:
        try:
            send_mail(
                subject="New Anonymous Feedback Posted — Strativ Voice",
                message=(
                    f"A new anonymous feedback has been posted on Strativ Voice:\n\n"
                    f"{post.content}\n\n"
                    f"View and respond here:\n{url}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=emails,
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Email notification failed: {e}")


def notify_new_comment(comment):
    """Notify about a new comment via Slack (public posts only) and email.

    The Slack message deliberately omits the commenter's role: for rare
    roles like CEO that was an instant deanonymiser. Internal app users
    still see the role badge in the UI (where the audience is bounded by
    `target_role` already).
    """
    post = comment.post
    url = _post_url(post)

    if not post.target_role:
        msg = (
            f":speech_balloon: *<{url}|New comment on feedback>*\n"
            f">{comment.content[:200]}"
        )
        send_slack_message(msg)

    if not getattr(settings, 'EMAIL_NOTIFICATION_ENABLED', True):
        return

    email_qs = NotificationEmail.objects.filter(notify_on_new_comment=True)
    if post.target_role:
        email_qs = email_qs.filter(role=post.target_role)
    else:
        email_qs = email_qs.filter(role__isnull=True)

    emails = list(email_qs.values_list('email', flat=True))
    if emails:
        try:
            send_mail(
                subject=f"New comment on feedback — Strativ Voice",
                message=(
                    f"A new comment has been added to a feedback post.\n\n"
                    f"Comment:\n{comment.content}\n\n"
                    f"View the full thread here:\n{url}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=emails,
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Email notification failed for comment: {e}")


def create_status_notification(post, actor=None):
    """Notify every subscriber of `post` that the status changed.

    Pre-rework this notified only `post.author`. The Subscription table
    means anyone with prior interest in the post (poster, commenters,
    favouriters) hears about the resolution — a small UX upgrade.

    `actor` is the HR/CEO user who triggered the update; we exclude them
    from the recipients so they don't notify themselves.
    """
    subscriber_ids = Subscription.objects.filter(post=post).values_list(
        'user_id', flat=True
    )
    if actor is not None:
        subscriber_ids = subscriber_ids.exclude(user_id=actor.pk)

    Notification.objects.bulk_create([
        Notification(
            recipient_id=uid,
            post=post,
            notification_type=Notification.TYPE_STATUS,
        )
        for uid in subscriber_ids
    ])


def create_comment_notifications(comment, actor=None):
    """Create in-app notifications for a new comment.

    Recipients are every subscriber of the post except the actor who
    just commented.
    """
    post = comment.post
    subscriber_ids = list(
        Subscription.objects.filter(post=post).values_list('user_id', flat=True)
    )
    if actor is not None:
        subscriber_ids = [uid for uid in subscriber_ids if uid != actor.pk]

    if subscriber_ids:
        Notification.objects.bulk_create([
            Notification(recipient_id=uid, post=post, comment=comment)
            for uid in subscriber_ids
        ])


def notify_status_update(post, updated_by):
    """Notify about a status update via Slack (public posts only)."""
    if post.target_role:
        return

    url = _post_url(post)
    eta_str = f" | ETA: {post.eta}" if post.eta else ""
    if post.status in ('done', 'rejected') and post.remark:
        preview = post.remark[:200]
    else:
        preview = post.content[:150]

    msg = (
        f":pencil2: *<{url}|Feedback>* status updated to *{post.get_status_display()}*{eta_str}\n"
        f">{preview}"
    )
    send_slack_message(msg)
