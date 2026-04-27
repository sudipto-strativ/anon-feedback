import json
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User

from feedback.models import Post, Comment, Vote, Favourite, UserProfile


def make_user(username='testuser', role='employee'):
    user = User.objects.create_user(username=username, password='pass')
    user.profile.role = role
    user.profile.save()
    return user


def make_post(author, content='Test content', status='pending'):
    return Post.objects.create(author=author, content=content, status=status)


class AuthRedirectTest(TestCase):
    """All @login_required views redirect unauthenticated users."""

    PROTECTED_URLS = [
        ('feed', []),
        ('list_view', []),
        ('post_create', []),
        ('favourites', []),
    ]

    def test_unauthenticated_redirects(self):
        client = Client()
        for name, args in self.PROTECTED_URLS:
            url = reverse(name, args=args)
            response = client.get(url)
            self.assertIn(response.status_code, [301, 302], f'{name} should redirect')


class FeedViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.client.login(username='testuser', password='pass')

    def test_get_recent_tab(self):
        make_post(self.user, 'Post 1')
        response = self.client.get(reverse('feed'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['current_tab'], 'recent')

    def test_get_top_tab(self):
        response = self.client.get(reverse('feed') + '?tab=top')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['current_tab'], 'top')

    def test_get_hot_tab(self):
        response = self.client.get(reverse('feed') + '?tab=hot')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['current_tab'], 'hot')

    def test_top_tab_sorts_by_score(self):
        post_low = make_post(self.user, 'low score')
        post_high = make_post(self.user, 'high score')
        other = make_user('other')
        Vote.objects.create(user=self.user, post=post_high, vote_type='like')
        Vote.objects.create(user=other, post=post_high, vote_type='like')
        Vote.objects.create(user=self.user, post=post_low, vote_type='dislike')
        response = self.client.get(reverse('feed') + '?tab=top')
        posts = list(response.context['posts'])
        self.assertEqual(posts[0].id, post_high.id)

    def test_vote_map_in_context(self):
        post = make_post(self.user)
        Vote.objects.create(user=self.user, post=post, vote_type='like')
        response = self.client.get(reverse('feed'))
        self.assertIn(post.id, response.context['user_vote_map'])
        self.assertEqual(response.context['user_vote_map'][post.id], 'like')

    def test_favourite_set_in_context(self):
        post = make_post(self.user)
        Favourite.objects.create(user=self.user, post=post)
        response = self.client.get(reverse('feed'))
        self.assertIn(post.id, response.context['favourite_set'])


class ListViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.client.login(username='testuser', password='pass')

    def test_get_returns_200(self):
        response = self.client.get(reverse('list_view'))
        self.assertEqual(response.status_code, 200)

    def test_status_filter(self):
        make_post(self.user, 'pending post', 'pending')
        make_post(self.user, 'done post', 'done')
        response = self.client.get(reverse('list_view') + '?status=done')
        posts = list(response.context['page_obj'])
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].status, 'done')

    def test_search_filter(self):
        make_post(self.user, 'unique keyword content')
        make_post(self.user, 'other content')
        response = self.client.get(reverse('list_view') + '?q=unique+keyword')
        posts = list(response.context['page_obj'])
        self.assertEqual(len(posts), 1)

    def test_pagination(self):
        for i in range(12):
            make_post(self.user, f'Post {i}')
        response = self.client.get(reverse('list_view'))
        self.assertEqual(len(response.context['page_obj']), 10)

    def test_context_contains_status_choices(self):
        response = self.client.get(reverse('list_view'))
        self.assertIn('STATUS_CHOICES', response.context)


class PostDetailViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.author = make_user('author')
        self.hr_user = make_user('hr_user', role='hr')
        self.employee = make_user('employee')
        self.post = make_post(self.author)

    def test_get_as_employee(self):
        self.client.login(username='employee', password='pass')
        response = self.client.get(reverse('post_detail', args=[self.post.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_update_status'])

    def test_get_as_hr_can_update_status(self):
        self.client.login(username='hr_user', password='pass')
        response = self.client.get(reverse('post_detail', args=[self.post.pk]))
        self.assertTrue(response.context['can_update_status'])
        self.assertIsNotNone(response.context['status_form'])

    def test_get_nonexistent_post_returns_404(self):
        self.client.login(username='employee', password='pass')
        response = self.client.get(reverse('post_detail', args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_post_comment_creates_comment(self):
        self.client.login(username='employee', password='pass')
        with patch('feedback.views.notify_new_comment'):
            response = self.client.post(
                reverse('post_detail', args=[self.post.pk]),
                {'content': 'My comment'},
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Comment.objects.filter(post=self.post).count(), 1)

    def test_post_empty_comment_no_image_invalid(self):
        self.client.login(username='employee', password='pass')
        response = self.client.post(
            reverse('post_detail', args=[self.post.pk]),
            {'content': ''},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Comment.objects.filter(post=self.post).count(), 0)

    def test_user_post_vote_in_context(self):
        self.client.login(username='employee', password='pass')
        Vote.objects.create(user=self.employee, post=self.post, vote_type='like')
        response = self.client.get(reverse('post_detail', args=[self.post.pk]))
        self.assertEqual(response.context['user_post_vote'], 'like')


class PostCreateViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.client.login(username='testuser', password='pass')

    def test_get_returns_200(self):
        response = self.client.get(reverse('post_create'))
        self.assertEqual(response.status_code, 200)

    def test_post_creates_post_and_redirects(self):
        with patch('feedback.views.notify_new_post'):
            response = self.client.post(reverse('post_create'), {'content': 'New feedback'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Post.objects.count(), 1)
        self.assertEqual(Post.objects.first().author, self.user)

    def test_post_invalid_form_no_content(self):
        response = self.client.post(reverse('post_create'), {'content': ''})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Post.objects.count(), 0)


class VotePostViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.other = make_user('other')
        self.client.login(username='testuser', password='pass')
        self.post = make_post(self.user)

    def _vote(self, vote_type):
        return self.client.post(
            reverse('vote_post', args=[self.post.pk]),
            data=json.dumps({'vote_type': vote_type}),
            content_type='application/json',
        )

    def test_new_like(self):
        response = self._vote('like')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['like_count'], 1)
        self.assertEqual(data['user_vote'], 'like')

    def test_toggle_off_same_vote(self):
        self._vote('like')
        response = self._vote('like')
        data = response.json()
        self.assertEqual(data['like_count'], 0)
        self.assertIsNone(data['user_vote'])

    def test_switch_vote(self):
        self._vote('like')
        response = self._vote('dislike')
        data = response.json()
        self.assertEqual(data['like_count'], 0)
        self.assertEqual(data['dislike_count'], 1)
        self.assertEqual(data['user_vote'], 'dislike')

    def test_invalid_vote_type(self):
        response = self._vote('meh')
        self.assertEqual(response.status_code, 400)

    def test_score_in_response(self):
        response = self._vote('like')
        data = response.json()
        self.assertIn('score', data)
        self.assertEqual(data['score'], 1)

    def test_get_not_allowed(self):
        response = self.client.get(reverse('vote_post', args=[self.post.pk]))
        self.assertEqual(response.status_code, 405)


class VoteCommentViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.client.login(username='testuser', password='pass')
        self.post = make_post(self.user)
        self.comment = Comment.objects.create(post=self.post, author=self.user, content='hi')

    def _vote(self, vote_type):
        return self.client.post(
            reverse('vote_comment', args=[self.comment.pk]),
            data=json.dumps({'vote_type': vote_type}),
            content_type='application/json',
        )

    def test_new_like(self):
        response = self._vote('like')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['like_count'], 1)
        self.assertEqual(data['user_vote'], 'like')

    def test_toggle_off(self):
        self._vote('dislike')
        response = self._vote('dislike')
        data = response.json()
        self.assertIsNone(data['user_vote'])

    def test_switch_vote(self):
        self._vote('like')
        response = self._vote('dislike')
        data = response.json()
        self.assertEqual(data['dislike_count'], 1)
        self.assertEqual(data['like_count'], 0)

    def test_invalid_vote_type(self):
        response = self._vote('bad')
        self.assertEqual(response.status_code, 400)


class UpdateStatusViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.employee = make_user('employee', role='employee')
        self.hr = make_user('hr', role='hr')
        self.ceo = make_user('ceo', role='ceo')
        self.post = make_post(self.employee)

    def test_employee_cannot_update_status(self):
        self.client.login(username='employee', password='pass')
        response = self.client.post(
            reverse('update_status', args=[self.post.pk]),
            {'status': 'in_progress', 'remark': '', 'eta': ''},
        )
        self.assertEqual(response.status_code, 403)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'pending')

    def test_hr_can_update_status(self):
        self.client.login(username='hr', password='pass')
        with patch('feedback.views.notify_status_update'):
            response = self.client.post(
                reverse('update_status', args=[self.post.pk]),
                {'status': 'in_progress', 'remark': '', 'eta': ''},
            )
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'in_progress')
        self.assertEqual(self.post.status_updated_by, self.hr)

    def test_ceo_can_update_status(self):
        self.client.login(username='ceo', password='pass')
        with patch('feedback.views.notify_status_update'):
            response = self.client.post(
                reverse('update_status', args=[self.post.pk]),
                {'status': 'done', 'remark': 'Fixed!', 'eta': ''},
            )
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'done')

    def test_done_requires_remark(self):
        self.client.login(username='hr', password='pass')
        self.client.post(
            reverse('update_status', args=[self.post.pk]),
            {'status': 'done', 'remark': '', 'eta': ''},
        )
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'pending')

    def test_get_not_allowed(self):
        self.client.login(username='hr', password='pass')
        response = self.client.get(reverse('update_status', args=[self.post.pk]))
        self.assertEqual(response.status_code, 405)


class ToggleFavouriteViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.client.login(username='testuser', password='pass')
        self.post = make_post(self.user)

    def _toggle(self):
        return self.client.post(reverse('toggle_favourite', args=[self.post.pk]))

    def test_add_favourite(self):
        response = self._toggle()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['is_favourite'])
        self.assertEqual(Favourite.objects.count(), 1)

    def test_remove_favourite(self):
        Favourite.objects.create(user=self.user, post=self.post)
        response = self._toggle()
        self.assertFalse(response.json()['is_favourite'])
        self.assertEqual(Favourite.objects.count(), 0)

    def test_get_not_allowed(self):
        response = self.client.get(reverse('toggle_favourite', args=[self.post.pk]))
        self.assertEqual(response.status_code, 405)


class FavouritesFeedViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = make_user()
        self.client.login(username='testuser', password='pass')

    def test_empty_favourites(self):
        response = self.client.get(reverse('favourites'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['posts']), 0)

    def test_shows_only_favourited_posts(self):
        post1 = make_post(self.user, 'fav post')
        make_post(self.user, 'not fav')
        Favourite.objects.create(user=self.user, post=post1)
        response = self.client.get(reverse('favourites'))
        posts = list(response.context['posts'])
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].id, post1.id)


class RegisterViewTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_get_register_page(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)

    def test_authenticated_user_redirected(self):
        user = make_user()
        self.client.login(username='testuser', password='pass')
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 302)

    def test_valid_registration_creates_user(self):
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'password1': 'Str0ng!Pass99',
            'password2': 'Str0ng!Pass99',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_registration_sets_employee_role(self):
        self.client.post(reverse('register'), {
            'username': 'newuser',
            'password1': 'Str0ng!Pass99',
            'password2': 'Str0ng!Pass99',
        })
        user = User.objects.get(username='newuser')
        self.assertEqual(user.profile.role, 'employee')

    def test_registration_logs_in_user(self):
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'password1': 'Str0ng!Pass99',
            'password2': 'Str0ng!Pass99',
        })
        # After successful registration user should be logged in — session set
        self.assertIn('_auth_user_id', self.client.session)

    def test_invalid_registration_no_redirect(self):
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'password1': 'pass1',
            'password2': 'pass2',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newuser').exists())


class BuildVoteMapTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.post = make_post(self.user)

    def test_empty_post_ids(self):
        from feedback.views import _build_vote_map
        result = _build_vote_map(self.user, [])
        self.assertEqual(result, {})

    def test_returns_correct_vote_type(self):
        from feedback.views import _build_vote_map
        Vote.objects.create(user=self.user, post=self.post, vote_type='like')
        result = _build_vote_map(self.user, [self.post.id])
        self.assertEqual(result, {self.post.id: 'like'})

    def test_excludes_comment_votes(self):
        from feedback.views import _build_vote_map
        comment = Comment.objects.create(post=self.post, author=self.user, content='hi')
        Vote.objects.create(user=self.user, comment=comment, vote_type='like')
        result = _build_vote_map(self.user, [self.post.id])
        self.assertEqual(result, {})


class BuildFavouriteSetTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.post = make_post(self.user)

    def test_empty_post_ids(self):
        from feedback.views import _build_favourite_set
        result = _build_favourite_set(self.user, [])
        self.assertEqual(result, {})

    def test_returns_favourited_post(self):
        from feedback.views import _build_favourite_set
        Favourite.objects.create(user=self.user, post=self.post)
        result = _build_favourite_set(self.user, [self.post.id])
        self.assertEqual(result, {self.post.id: True})

    def test_non_favourited_post_excluded(self):
        from feedback.views import _build_favourite_set
        result = _build_favourite_set(self.user, [self.post.id])
        self.assertNotIn(self.post.id, result)
