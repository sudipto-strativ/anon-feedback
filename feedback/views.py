import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import CommentForm, PostForm, RegisterForm, StatusUpdateForm
from .models import Comment, Favourite, Post, Vote
from .notifications import notify_new_comment, notify_new_post, notify_status_update


def _build_vote_map(user, post_ids):
    """Return {post_id: vote_type} for the given user and post ids."""
    if not post_ids:
        return {}
    votes = Vote.objects.filter(
        user=user, post_id__in=post_ids, comment__isnull=True
    ).values('post_id', 'vote_type')
    return {v['post_id']: v['vote_type'] for v in votes}


def _build_favourite_set(user, post_ids):
    """Return {post_id: True} for posts the user has favourited."""
    if not post_ids:
        return {}
    return {
        pk: True for pk in Favourite.objects.filter(
            user=user, post_id__in=post_ids
        ).values_list('post_id', flat=True)
    }


@login_required
def feed(request):
    """Main feed view with tab-based sorting."""
    current_tab = request.GET.get('tab', 'recent')

    posts = Post.objects.select_related('author', 'author__profile').prefetch_related(
        'votes', 'comments'
    )

    if current_tab == 'top':
        # Sort by score (likes - dislikes) — annotate via Python since score is a property
        posts = list(posts)
        posts.sort(key=lambda p: p.score, reverse=True)
    elif current_tab == 'hot':
        # Most comments in last 7 days
        seven_days_ago = timezone.now() - timedelta(days=7)
        posts = posts.annotate(
            recent_comment_count=Count(
                'comments',
                filter=Q(comments__created_at__gte=seven_days_ago)
            )
        ).order_by('-recent_comment_count', '-created_at')
    else:
        # Default: recent
        posts = posts.order_by('-created_at')

    post_ids = [p.id for p in posts] if isinstance(posts, list) else list(posts.values_list('id', flat=True))

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

    posts = Post.objects.select_related('author', 'author__profile').prefetch_related(
        'votes', 'comments'
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
def post_detail(request, pk):
    """Post detail view with comment submission."""
    post = get_object_or_404(
        Post.objects.select_related('author', 'author__profile', 'status_updated_by'),
        pk=pk
    )
    comments = post.comments.select_related('author', 'author__profile').prefetch_related('votes')

    # User's vote on the post
    user_post_vote = None
    try:
        vote = Vote.objects.get(user=request.user, post=post, comment__isnull=True)
        user_post_vote = vote.vote_type
    except Vote.DoesNotExist:
        pass

    # User's votes on comments
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

    # Check if user can update status
    can_update_status = False
    try:
        role = request.user.profile.role
        if role in ('ceo', 'hr'):
            can_update_status = True
            status_form = StatusUpdateForm(instance=post)
    except Exception:
        pass

    if request.method == 'POST':
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.post = post
            comment.author = request.user
            comment.save()
            notify_new_comment(comment)
            messages.success(request, 'Your comment has been posted.')
            return redirect('post_detail', pk=pk)

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
        form = PostForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            notify_new_post(post)
            messages.success(request, 'Your feedback has been posted anonymously.')
            return redirect('feed')
    else:
        form = PostForm()

    return render(request, 'feedback/post_create.html', {'form': form})


@login_required
@require_POST
def vote_post(request, pk):
    """Toggle vote on a post. Returns JSON with updated counts."""
    post = get_object_or_404(Post, pk=pk)

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
            # Same vote — toggle off (delete)
            existing_vote.delete()
            user_vote = None
        else:
            # Different vote — update
            existing_vote.vote_type = vote_type
            existing_vote.save()
            user_vote = vote_type
    else:
        # New vote
        Vote.objects.create(user=request.user, post=post, vote_type=vote_type)
        user_vote = vote_type

    # Re-fetch counts
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
    comment = get_object_or_404(Comment, pk=pk)

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
def update_status(request, pk):
    """Update the status of a post. Only CEO and HR can do this."""
    post = get_object_or_404(Post, pk=pk)

    # Check role
    try:
        role = request.user.profile.role
    except Exception:
        role = 'employee'

    if role not in ('ceo', 'hr'):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    form = StatusUpdateForm(request.POST, instance=post)
    if form.is_valid():
        updated_post = form.save(commit=False)
        updated_post.status_updated_by = request.user
        updated_post.save()
        notify_status_update(updated_post, request.user)
        messages.success(request, f'Status updated to "{updated_post.get_status_display()}".')
        return redirect('post_detail', pk=pk)

    # Form invalid — re-render detail page with errors
    for field, errors in form.errors.items():
        for error in errors:
            messages.error(request, error)
    return redirect('post_detail', pk=pk)


@login_required
@require_POST
def toggle_favourite(request, pk):
    """Toggle a post as favourite. Returns JSON {is_favourite: bool}."""
    post = get_object_or_404(Post, pk=pk)
    fav = Favourite.objects.filter(user=request.user, post=post).first()
    if fav:
        fav.delete()
        is_favourite = False
    else:
        Favourite.objects.create(user=request.user, post=post)
        is_favourite = True
    return JsonResponse({'is_favourite': is_favourite})


@login_required
def favourites_feed(request):
    """Feed showing only the current user's favourited posts."""
    favourited_post_ids = Favourite.objects.filter(
        user=request.user
    ).values_list('post_id', flat=True)

    posts = Post.objects.filter(
        id__in=favourited_post_ids
    ).select_related('author', 'author__profile').prefetch_related(
        'votes', 'comments'
    ).order_by('-created_at')

    post_ids = list(posts.values_list('id', flat=True))

    return render(request, 'feedback/favourites.html', {
        'posts': posts,
        'user_vote_map': _build_vote_map(request.user, post_ids),
        'favourite_set': _build_favourite_set(request.user, post_ids),
    })


def register(request):
    """Register a new user with employee role."""
    if request.user.is_authenticated:
        return redirect('feed')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            # UserProfile is created by signal, but ensure role is 'employee'
            try:
                profile = user.profile
                profile.role = 'employee'
                profile.save()
            except Exception:
                from .models import UserProfile
                UserProfile.objects.get_or_create(user=user, defaults={'role': 'employee'})

            login(request, user)
            messages.success(request, f'Welcome to Strativ Voice, {user.username}!')
            return redirect('feed')
    else:
        form = RegisterForm()

    return render(request, 'feedback/register.html', {'form': form})
