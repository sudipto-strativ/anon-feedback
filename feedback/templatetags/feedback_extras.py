from django import template
from django.utils import timezone
from django.utils.timesince import timesince

register = template.Library()


@register.filter
def timesince_short(value):
    """Return a short human-readable time since the given date."""
    if not value:
        return ''
    try:
        now = timezone.now()
        # Make value timezone-aware if it isn't
        if timezone.is_naive(value):
            value = timezone.make_aware(value)

        delta = now - value
        seconds = int(delta.total_seconds())

        if seconds < 60:
            return 'just now'
        elif seconds < 3600:
            mins = seconds // 60
            return f'{mins}m ago'
        elif seconds < 86400:
            hours = seconds // 3600
            return f'{hours}h ago'
        elif seconds < 86400 * 7:
            days = seconds // 86400
            return f'{days}d ago'
        elif seconds < 86400 * 30:
            weeks = seconds // (86400 * 7)
            return f'{weeks}w ago'
        elif seconds < 86400 * 365:
            months = seconds // (86400 * 30)
            return f'{months}mo ago'
        else:
            years = seconds // (86400 * 365)
            return f'{years}y ago'
    except Exception:
        return ''


@register.filter
def truncate_chars(value, max_length):
    """Truncate a string to a maximum number of characters."""
    if not value:
        return ''
    value = str(value)
    if len(value) <= max_length:
        return value
    return value[:max_length].rstrip() + '...'


@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary by key."""
    if not dictionary:
        return None
    return dictionary.get(key)


@register.filter
def score_class(score):
    """Return a CSS class based on score value."""
    try:
        score = int(score)
        if score > 0:
            return 'positive'
        elif score < 0:
            return 'negative'
        return 'neutral'
    except (ValueError, TypeError):
        return 'neutral'


AVATAR_GRADIENTS = [
    'linear-gradient(135deg,#7c3aed,#a855f7)',  # violet
    'linear-gradient(135deg,#f43f5e,#fb7185)',  # rose
    'linear-gradient(135deg,#0ea5e9,#38bdf8)',  # sky
    'linear-gradient(135deg,#059669,#34d399)',  # emerald
    'linear-gradient(135deg,#f59e0b,#fbbf24)',  # amber
    'linear-gradient(135deg,#ec4899,#f472b6)',  # pink
    'linear-gradient(135deg,#06b6d4,#67e8f9)',  # cyan
    'linear-gradient(135deg,#8b5cf6,#c084fc)',  # purple
]

@register.filter
def avatar_gradient(post_id):
    """Return a deterministic gradient string based on post id."""
    try:
        return AVATAR_GRADIENTS[int(post_id) % len(AVATAR_GRADIENTS)]
    except (TypeError, ValueError):
        return AVATAR_GRADIENTS[0]


@register.simple_tag
def user_role_badge(user):
    """Return a role badge HTML for a user."""
    try:
        role = user.profile.role
        if role == 'hr':
            return f'<span class="role-badge-hr">HR</span>'
        elif role == 'ceo':
            return f'<span class="role-badge-ceo">CEO</span>'
        else:
            return f'<span class="role-badge-employee">Employee</span>'
    except Exception:
        return '<span class="role-badge-employee">Employee</span>'
