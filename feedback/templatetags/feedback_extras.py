from django import template
from django.utils import timezone
from django.utils.timesince import timesince
from django.utils.safestring import mark_safe
import markdown
import bleach

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


_MD_ALLOWED_TAGS = [
    'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'strong', 'em', 'del', 's', 'code', 'pre', 'blockquote',
    'ul', 'ol', 'li', 'hr', 'br', 'a', 'img',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
]
_MD_ALLOWED_ATTRS = {
    'a':   ['href', 'title', 'rel'],
    'img': ['src', 'alt', 'title'],
    'code': ['class'],
    'pre':  ['class'],
    'th':   ['align'],
    'td':   ['align'],
}


@register.filter(is_safe=True)
def render_markdown(value):
    """Render markdown text to sanitized HTML."""
    if not value:
        return ''
    html = markdown.markdown(
        value,
        extensions=['fenced_code', 'tables', 'nl2br', 'sane_lists'],
    )
    clean = bleach.clean(html, tags=_MD_ALLOWED_TAGS, attributes=_MD_ALLOWED_ATTRS, strip=True)
    return mark_safe(clean)


# Strativ branding forbids gradients — flat colour palette only.
# Brand orange leads, warm-black anchors, with the Strativ data-viz scale
# providing the rest of the categorical hues.
AVATAR_COLORS = [
    '#FE5001',  # strativ orange
    '#1A0E1C',  # warm black
    '#1570EF',  # info blue
    '#0E9384',  # teal
    '#F9B70E',  # brand yellow
    '#7A5AF8',  # violet (data-viz, not brand)
    '#475467',  # slate
    '#039855',  # success green
]


@register.filter
def avatar_gradient(post_id):
    """Return a deterministic solid colour based on post id.

    Filter name kept for template compatibility; Strativ branding rules
    out gradients so this now returns a flat colour token.
    """
    try:
        return AVATAR_COLORS[int(post_id) % len(AVATAR_COLORS)]
    except (TypeError, ValueError):
        return AVATAR_COLORS[0]


@register.simple_tag
def user_role_badge(user):
    """Return a role badge HTML for a user."""
    try:
        role = user.profile.role
        if role == 'hr':
            return f'<span class="role-badge-hr">HR</span>'
        elif role == 'ceo':
            return f'<span class="role-badge-ceo">CEO</span>'
        elif role == 'admin':
            return f'<span class="role-badge-admin">Admin</span>'
        else:
            return f'<span class="role-badge-employee">Member</span>'
    except Exception:
        return '<span class="role-badge-employee">Member</span>'
