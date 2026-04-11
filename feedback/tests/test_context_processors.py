from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User, AnonymousUser

from feedback.models import Post
from feedback.context_processors import sidebar_stats


def make_user(username='testuser'):
    return User.objects.create_user(username=username, password='pass')


def make_post(author, status='pending'):
    return Post.objects.create(author=author, content='Test', status=status)


class SidebarStatsContextProcessorTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = make_user()

    def _request(self, user=None):
        request = self.factory.get('/')
        request.user = user or self.user
        return request

    def test_unauthenticated_returns_empty(self):
        request = self._request(AnonymousUser())
        result = sidebar_stats(request)
        self.assertEqual(result, {})

    def test_authenticated_returns_stats(self):
        result = sidebar_stats(self._request())
        self.assertIn('total_posts', result)
        self.assertIn('in_progress_posts', result)
        self.assertIn('resolved_posts', result)

    def test_total_posts_count(self):
        make_post(self.user, 'pending')
        make_post(self.user, 'done')
        result = sidebar_stats(self._request())
        self.assertEqual(result['total_posts'], 2)

    def test_in_progress_count(self):
        make_post(self.user, 'pending')
        make_post(self.user, 'in_progress')
        make_post(self.user, 'in_progress')
        result = sidebar_stats(self._request())
        self.assertEqual(result['in_progress_posts'], 2)

    def test_resolved_count(self):
        make_post(self.user, 'done')
        make_post(self.user, 'pending')
        result = sidebar_stats(self._request())
        self.assertEqual(result['resolved_posts'], 1)

    def test_empty_db_returns_zeros(self):
        result = sidebar_stats(self._request())
        self.assertEqual(result['total_posts'], 0)
        self.assertEqual(result['in_progress_posts'], 0)
        self.assertEqual(result['resolved_posts'], 0)
