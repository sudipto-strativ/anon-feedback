"""Strativ Voice views.

The big shape change vs. the pre-anonymity-hardening version: Post and
Comment no longer carry an author FK. The implications that ripple
through this file are:

- Visibility checks for `target_role` posts can no longer ask "did I
  author this?" — we ask "have I subscribed?" instead, since
  `Subscription` is auto-created when a user posts, comments, or
  favourites. This means the author of a private post keeps being
  able to see it, and so does anyone who's interacted with it.
- All `select_related('author', ...)` joins are gone.
- All `<int:pk>` URL kwargs are now `<uuid:public_id>`.
- `post_create` / comment-creation / `toggle_favourite` now end with a
  `Subscription.objects.get_or_create(...)` call so the actor is added
  to the interest graph and receives downstream in-app notifications.
"""

import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import CommentForm, PostForm, RegisterForm, StatusUpdateForm
from .models import (
    Comment,
    CommentImage,
    Favourite,
    Notification,
    Post,
    PostAttachment,
    Subscription,
    UserProfile,
    Vote,
)
from .notifications import (
    create_comment_notifications,
    create_status_notification,
    notify_new_comment,
    notify_new_post,
    notify_status_update,
)


def _user_role(user):
    try:
        return user.profile.role
    except Exception:
        return None


def _subscribed_post_ids(user):
    """Posts this user is interested in (auto-subscribed because they
    posted, commented, or favourited). Used as the "did I author this"
    substitute for target_role visibility checks."""
    return set(
        Subscription.objects.filter(user=user).values_list('post_id', flat=True)
    )


def _visible_posts_q(user):
    """Q filter for posts this user can see.

    A user may see a post if:
      * the post is public (`target_role` is null), OR
      * the user's role matches the post's `target_role`, OR
      * the user is subscribed to the post (which, post-migration,
        covers the previous "I authored this" case — the author auto-
        subscribed on create — plus commenters and favouriters).
    """
    role = _user_role(user)
    subscribed_ids = _subscribed_post_ids(user)
    return (
        Q(target_role__isnull=True)
        | Q(target_role=role)
        | Q(id__in=subscribed_ids)
    )


def _can_view_post(user, post):
    if post.target_role is None:
        return True
    if _user_role(user) == post.target_role:
        return True
    return Subscription.objects.filter(user=user, post=post).exists()


def _build_vote_map(user, post_ids):
    if not post_ids:
        return {}
    votes = Vote.objects.filter(
        user=user, post_id__in=post_ids, comment__isnull=True
    ).values('post_id', 'vote_type')
    return {v['post_id']: v['vote_type'] for v in votes}


def _build_favourite_set(user, post_ids):
    if not post_ids:
        return {}
    return {
        pk: True for pk in Favourite.objects.filter(
            user=user, post_id__in=post_ids
        ).values_list('post_id', flat=True)
    }


def _auto_subscribe(user, post):
    """Add the actor to the post's interest graph. Idempotent."""
    Subscription.objects.get_or_create(user=user, post=post)


@login_required
def feed(request):
    """Main feed view with tab-based sorting."""
    current_tab = request.GET.get('tab', 'recent')

    posts = Post.objects.filter(_visible_posts_q(request.user)).prefetch_related(
        'votes', 'comments', 'attachments'
    )

    if current_tab == 'top':
        # Sort by score (likes - dislikes) — score is a property, so sort in Python.
        posts = list(posts)
        posts.sort(key=lambda p: p.score, reverse=True)
    elif current_tab == 'hot':
        seven_days_ago = timezone.now() - timedelta(days=7)
        posts = posts.annotate(
            recent_comment_count=Count(
                'comments',
                filter=Q(comments__created_at__gte=seven_days_ago)
            )
        ).order_by('-recent_comment_count', '-created_at')
    else:
        posts = posts.order_by('-created_at')

    post_ids = (
        [p.id for p in posts]
        if isinstance(posts, list)
        else list(posts.values_list('id', flat=True))
    )

    return render(request, 'feedback/feed.html', {
        'posts': posts,
        'current_tab': current_tab,
        'user_vote_map': _build_vote_map(request.user, post_ids),
        'favourite_set': _build_favourite_set(request.user, post_ids),
    })


@login_required
def list_view(request):
    """List view with search and status filter."""
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('q', '').strip()

    posts = Post.objects.filter(_visible_posts_q(request.user)).prefetch_related(
        'votes', 'comments', 'attachments'
    )

    if status_filter:
        posts = posts.filter(status=status_filter)

    if search_query:
        posts = posts.filter(content__icontains=search_query)

    posts = posts.order_by('-created_at')

    paginator = Paginator(posts, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    page_post_ids = [p.id for p in page_obj]

    return render(request, 'feedback/list_view.html', {
        'posts': page_obj,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search_query': search_query,
        'STATUS_CHOICES': Post.STATUS_CHOICES,
        'user_vote_map': _build_vote_map(request.user, page_post_ids),
        'favourite_set': _build_favourite_set(request.user, page_post_ids),
    })


@login_required
def post_detail(request, public_id):
    """Post detail view with comment submission."""
    post = get_object_or_404(
        Post.objects.select_related('status_updated_by').prefetch_related('attachments'),
        public_id=public_id,
    )
    if not _can_view_post(request.user, post):
        raise PermissionDenied
    comments = post.comments.prefetch_related('votes', 'images')

    user_post_vote = None
    try:
        vote = Vote.objects.get(user=request.user, post=post, comment__isnull=True)
        user_post_vote = vote.vote_type
    except Vote.DoesNotExist:
        pass

    comment_vote_map = {}
    comment_ids = [c.id for c in comments]
    if comment_ids:
        comment_votes = Vote.objects.filter(
            user=request.user,
            comment_id__in=comment_ids,
            post__isnull=True,
        ).values('comment_id', 'vote_type')
        for v in comment_votes:
            comment_vote_map[v['comment_id']] = v['vote_type']

    comment_form = CommentForm()
    status_form = None
    can_update_status = False
    role = _user_role(request.user)
    if role in ('ceo', 'hr', 'admin'):
        can_update_status = True
        status_form = StatusUpdateForm(instance=post)

    if request.method == 'POST':
        comment_form = CommentForm(request.POST, request.FILES)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.post = post
            # Snapshot the role at the moment of speaking. We don't store
            # who is speaking — that's the whole point of the rework.
            comment.role = role or 'employee'
            comment.save()
            if comment_form.cleaned_data.get('image'):
                CommentImage.objects.create(
                    comment=comment, image=comment_form.cleaned_data['image']
                )
            # Subscribe the commenter so they get notifications for
            # subsequent comments / status updates on this post.
            _auto_subscribe(request.user, post)
            notify_new_comment(comment)
            create_comment_notifications(comment, actor=request.user)
            messages.success(request, 'Your comment has been posted.')
            return redirect('post_detail', public_id=post.public_id)

    return render(request, 'feedback/post_detail.html', {
        'post': post,
        'comments': comments,
        'comment_form': comment_form,
        'status_form': status_form,
        'can_update_status': can_update_status,
        'user_post_vote': user_post_vote,
        'comment_vote_map': comment_vote_map,
    })


@login_required
def post_create(request):
    """Create a new feedback post."""
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            # No author assignment. Anonymous means anonymous.
            post.save()
            for f in form.cleaned_data.get('attachments') or []:
                PostAttachment.objects.create(post=post, file=f)
            # The original poster is the first subscriber, so they
            # keep getting in-app notifications on their own post.
            _auto_subscribe(request.user, post)
            notify_new_post(post)
            messages.success(request, 'Your feedback has been posted anonymously.')
            return redirect('feed')
    else:
        form = PostForm()

    return render(request, 'feedback/post_create.html', {'form': form})


@login_required
@require_POST
def vote_post(request, public_id):
    """Toggle vote on a post. Returns JSON with updated counts."""
    post = get_object_or_404(Post, public_id=public_id)
    if not _can_view_post(request.user, post):
        return JsonResponse({'error': 'Not found'}, status=404)

    try:
        data = json.loads(request.body)
        vote_type = data.get('vote_type')
    except (json.JSONDecodeError, AttributeError):
        vote_type = request.POST.get('vote_type')

    if vote_type not in ('like', 'dislike'):
        return JsonResponse({'error': 'Invalid vote type'}, status=400)

    existing_vote = Vote.objects.filter(
        user=request.user, post=post, comment__isnull=True
    ).first()

    user_vote = None
    if existing_vote:
        if existing_vote.vote_type == vote_type:
            existing_vote.delete()
            user_vote = None
        else:
            existing_vote.vote_type = vote_type
            existing_vote.save()
            user_vote = vote_type
    else:
        Vote.objects.create(user=request.user, post=post, vote_type=vote_type)
        user_vote = vote_type

    post.refresh_from_db()
    like_count = post.votes.filter(vote_type='like').count()
    dislike_count = post.votes.filter(vote_type='dislike').count()
    score = like_count - dislike_count

    return JsonResponse({
        'score': score,
        'like_count': like_count,
        'dislike_count': dislike_count,
        'user_vote': user_vote,
    })


@login_required
@require_POST
def vote_comment(request, pk):
    """Toggle vote on a comment. Returns JSON with updated counts."""
    comment = get_object_or_404(Comment.objects.select_related('post'), pk=pk)
    if not _can_view_post(request.user, comment.post):
        return JsonResponse({'error': 'Not found'}, status=404)

    try:
        data = json.loads(request.body)
        vote_type = data.get('vote_type')
    except (json.JSONDecodeError, AttributeError):
        vote_type = request.POST.get('vote_type')

    if vote_type not in ('like', 'dislike'):
        return JsonResponse({'error': 'Invalid vote type'}, status=400)

    existing_vote = Vote.objects.filter(
        user=request.user, comment=comment, post__isnull=True
    ).first()

    user_vote = None
    if existing_vote:
        if existing_vote.vote_type == vote_type:
            existing_vote.delete()
            user_vote = None
        else:
            existing_vote.vote_type = vote_type
            existing_vote.save()
            user_vote = vote_type
    else:
        Vote.objects.create(user=request.user, comment=comment, vote_type=vote_type)
        user_vote = vote_type

    like_count = comment.votes.filter(vote_type='like').count()
    dislike_count = comment.votes.filter(vote_type='dislike').count()
    score = like_count - dislike_count

    return JsonResponse({
        'score': score,
        'like_count': like_count,
        'dislike_count': dislike_count,
        'user_vote': user_vote,
    })


@login_required
@require_POST
def update_status(request, public_id):
    """Update the status of a post. Only CEO/HR/Admin can do this."""
    post = get_object_or_404(Post, public_id=public_id)
    if not _can_view_post(request.user, post):
        return JsonResponse({'error': 'Not found'}, status=404)

    role = _user_role(request.user) or 'employee'
    if role not in ('ceo', 'hr', 'admin'):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    form = StatusUpdateForm(request.POST, instance=post)
    if form.is_valid():
        updated_post = form.save(commit=False)
        updated_post.status_updated_by = request.user
        updated_post.save()
        notify_status_update(updated_post, request.user)
        create_status_notification(updated_post, actor=request.user)
        messages.success(request, f'Status updated to "{updated_post.get_status_display()}".')
        return redirect('post_detail', public_id=post.public_id)

    for field, errors in form.errors.items():
        for error in errors:
            messages.error(request, error)
    return redirect('post_detail', public_id=post.public_id)


@login_required
@require_POST
def toggle_favourite(request, public_id):
    """Toggle a post as favourite. Returns JSON {is_favourite: bool}.

    Toggling on auto-subscribes (you'll get notifications). Toggling off
    does NOT unsubscribe — once you're interested, you're interested.
    """
    post = get_object_or_404(Post, public_id=public_id)
    if not _can_view_post(request.user, post):
        return JsonResponse({'error': 'Not found'}, status=404)
    fav = Favourite.objects.filter(user=request.user, post=post).first()
    if fav:
        fav.delete()
        is_favourite = False
    else:
        Favourite.objects.create(user=request.user, post=post)
        _auto_subscribe(request.user, post)
        is_favourite = True
    return JsonResponse({'is_favourite': is_favourite})


@login_required
def favourites_feed(request):
    """Feed showing only the current user's favourited posts."""
    favourited_post_ids = Favourite.objects.filter(
        user=request.user
    ).values_list('post_id', flat=True)

    posts = Post.objects.filter(
        _visible_posts_q(request.user), id__in=favourited_post_ids
    ).prefetch_related('votes', 'comments', 'attachments').order_by('-created_at')

    post_ids = list(posts.values_list('id', flat=True))

    return render(request, 'feedback/favourites.html', {
        'posts': posts,
        'user_vote_map': _build_vote_map(request.user, post_ids),
        'favourite_set': _build_favourite_set(request.user, post_ids),
    })


@login_required
def notifications_list(request):
    """Show all notifications for the current user; marks them all as read."""
    notifications = (
        Notification.objects
        .filter(recipient=request.user)
        .select_related('post', 'comment')
    )
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return render(request, 'feedback/notifications.html', {'notifications': notifications})


@login_required
@require_POST
def mark_notifications_read(request):
    """Mark all unread notifications as read. Returns JSON {unread_count: 0}."""
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'unread_count': 0})


def register(request):
    """Register a new user with employee role."""
    if request.user.is_authenticated:
        return redirect('feed')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            try:
                profile = user.profile
                profile.role = 'employee'
                profile.save()
            except Exception:
                UserProfile.objects.get_or_create(user=user, defaults={'role': 'employee'})

            login(request, user)
            messages.success(request, f'Welcome to Strativ Voice, {user.username}!')
            return redirect('feed')
    else:
        form = RegisterForm()

    return render(request, 'feedback/register.html', {'form': form})
