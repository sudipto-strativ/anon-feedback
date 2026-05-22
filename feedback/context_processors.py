from .models import Notification, Post


def sidebar_stats(request):
    """Provide sidebar statistics and notification data for authenticated users."""
    if request.user.is_authenticated:
        total = Post.objects.count()
        in_progress = Post.objects.filter(status='in_progress').count()
        resolved = Post.objects.filter(status='done').count()
        unread_notification_count = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
        recent_notifications = list(
            Notification.objects
            .filter(recipient=request.user)
            # No `comment__author` join: Comment dropped its author FK as
            # part of the anonymity hardening. Templates read `comment.role`
            # directly off the row.
            .select_related('post', 'comment')
            .order_by('-created_at')[:8]
        )
        return {
            'total_posts': total,
            'in_progress_posts': in_progress,
            'resolved_posts': resolved,
            'unread_notification_count': unread_notification_count,
            'recent_notifications': recent_notifications,
        }
    return {}
