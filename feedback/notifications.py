import requests
import logging
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from .models import NotificationEmail, SlackConfig

logger = logging.getLogger(__name__)


def send_slack_message(text):
    """Send a message to Slack via webhook."""
    config = SlackConfig.objects.filter(is_active=True).first()
    if not config:
        # Fall back to settings-level webhook URL if configured
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
    """Return the absolute URL for a post detail page."""
    site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').rstrip('/')
    return site_url + reverse('post_detail', args=[post.id])


def notify_new_post(post):
    """Notify admins about a new post via Slack and email."""
    url = _post_url(post)
    msg = (
        f":mega: *<{url}|New Feedback Posted>*\n"
        f">{post.content[:200]}"
    )
    send_slack_message(msg)

    if not getattr(settings, 'EMAIL_NOTIFICATION_ENABLED', True):
        return

    emails = list(NotificationEmail.objects.filter(notify_on_new_post=True).values_list('email', flat=True))
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
    """Notify about a new comment via Slack and email."""
    post = comment.post
    url = _post_url(post)

    try:
        role_display = comment.author.profile.role_display
    except Exception:
        role_display = 'Employee'

    msg = (
        f":speech_balloon: *<{url}|New Comment>* · _{role_display}_\n"
        f">{comment.content[:200]}"
    )
    send_slack_message(msg)

    if not getattr(settings, 'EMAIL_NOTIFICATION_ENABLED', True):
        return

    emails = list(NotificationEmail.objects.filter(notify_on_new_comment=True).values_list('email', flat=True))
    if emails:
        try:
            send_mail(
                subject=f"New Comment on Feedback #{post.id} — Strativ Voice",
                message=(
                    f"A new comment has been added to Feedback #{post.id}.\n\n"
                    f"Comment:\n{comment.content}\n\n"
                    f"View the full thread here:\n{url}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=emails,
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Email notification failed for comment: {e}")


def notify_status_update(post, updated_by):
    """Notify about a status update via Slack."""
    url = _post_url(post)
    eta_str = f" | ETA: {post.eta}" if post.eta else ""
    if post.status in ('done', 'rejected') and post.remark:
        preview = post.remark[:200]
    else:
        preview = post.content[:150]

    msg = (
        f":pencil2: *<{url}|Feedback #{post.id}>* status updated to *{post.get_status_display()}*{eta_str}\n"
        f">{preview}"
    )
    send_slack_message(msg)
