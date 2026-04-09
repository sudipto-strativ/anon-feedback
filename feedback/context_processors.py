from .models import Post


def sidebar_stats(request):
    """Provide sidebar statistics for authenticated users."""
    if request.user.is_authenticated:
        total = Post.objects.count()
        in_progress = Post.objects.filter(status='in_progress').count()
        resolved = Post.objects.filter(status='done').count()
        return {
            'total_posts': total,
            'in_progress_posts': in_progress,
            'resolved_posts': resolved,
        }
    return {}
