"""End-to-end tests that the Subscription interest graph correctly
replaces the dropped author FK for notification routing.

What the view layer is supposed to do:

- post_create: subscribes the actor.
- post_detail (POST = new comment): subscribes the commenter.
- toggle_favourite (when turning on): subscribes the favouriter.
- update_status: generates a Notification for every subscriber except
  the HR/CEO/admin who pressed the button.
- a new comment: generates a Notification for every subscriber except
  the commenter.
"""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from feedback.models import (
    Comment,
    Favourite,
    Notification,
    Post,
    Subscription,
)


def _user(username, role='employee'):
    u = User.objects.create_user(username=username, password='p')
    u.profile.role = role
    u.profile.save()
    return u


class AutoSubscribeOnPostCreateTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _user('alice')
        self.client.login(username='alice', password='p')

    @patch('feedback.views.notify_new_post')
    def test_post_creation_subscribes_the_actor(self, _mock_notify):
        response = self.client.post(reverse('post_create'), {'content': 'hello'})
        self.assertEqual(response.status_code, 302)
        post = Post.objects.get()
        self.assertTrue(
            Subscription.objects.filter(user=self.user, post=post).exists()
        )


class AutoSubscribeOnCommentTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.author = _user('original')
        self.commenter = _user('observer')
        self.post = Post.objects.create(content='hello')
        Subscription.objects.create(user=self.author, post=self.post)

    @patch('feedback.views.notify_new_comment')
    @patch('feedback.views.create_comment_notifications')
    def test_commenting_subscribes_the_commenter(self, _mock_in_app, _mock_slack):
        self.client.login(username='observer', password='p')
        self.client.post(
            reverse('post_detail', args=[self.post.public_id]),
            {'content': 'a reply'},
        )
        self.assertTrue(
            Subscription.objects.filter(user=self.commenter, post=self.post).exists()
        )


class AutoSubscribeOnFavouriteTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _user('fan')
        self.post = Post.objects.create(content='popular')
        self.client.login(username='fan', password='p')

    def test_favouriting_subscribes_the_user(self):
        self.client.post(reverse('toggle_favourite', args=[self.post.public_id]))
        self.assertTrue(
            Subscription.objects.filter(user=self.user, post=self.post).exists()
        )

    def test_unfavouriting_does_not_unsubscribe(self):
        # Toggle on, then off. The Subscription must stick around so
        # the user keeps getting notifications on a post they once
        # cared about.
        self.client.post(reverse('toggle_favourite', args=[self.post.public_id]))
        self.client.post(reverse('toggle_favourite', args=[self.post.public_id]))
        self.assertFalse(Favourite.objects.filter(user=self.user, post=self.post).exists())
        self.assertTrue(
            Subscription.objects.filter(user=self.user, post=self.post).exists()
        )


class CommentNotificationsGoToSubscribersTest(TestCase):
    def setUp(self):
        self.original = _user('originalposter')
        self.lurker = _user('lurker')
        self.commenter = _user('commenter', role='hr')
        self.post = Post.objects.create(content='discuss')
        # Original poster + a lurker (e.g. a favouriter) subscribed.
        # The commenter will get added by the view code.
        Subscription.objects.create(user=self.original, post=self.post)
        Subscription.objects.create(user=self.lurker, post=self.post)

    @patch('feedback.views.notify_new_comment')
    def test_subscribers_minus_actor_get_in_app_notifications(self, _mock_slack):
        client = Client()
        client.login(username='commenter', password='p')
        client.post(
            reverse('post_detail', args=[self.post.public_id]),
            {'content': 'thanks for the feedback'},
        )
        recipients = set(
            Notification.objects.filter(post=self.post).values_list('recipient_id', flat=True)
        )
        # Original poster + lurker get notified.
        self.assertEqual(recipients, {self.original.pk, self.lurker.pk})
        # The commenter does NOT notify themselves.
        self.assertNotIn(self.commenter.pk, recipients)


class StatusUpdateNotificationsTest(TestCase):
    def setUp(self):
        self.original = _user('originalposter')
        self.lurker = _user('lurker')
        self.hr = _user('hrperson', role='hr')
        self.post = Post.objects.create(content='please fix this')
        Subscription.objects.create(user=self.original, post=self.post)
        Subscription.objects.create(user=self.lurker, post=self.post)
        Subscription.objects.create(user=self.hr, post=self.post)

    @patch('feedback.views.notify_status_update')
    def test_status_change_notifies_subscribers_not_actor(self, _mock_slack):
        client = Client()
        client.login(username='hrperson', password='p')
        response = client.post(
            reverse('update_status', args=[self.post.public_id]),
            {'status': 'in_progress', 'remark': '', 'eta': ''},
        )
        self.assertEqual(response.status_code, 302)
        recipients = set(
            Notification.objects.filter(post=self.post).values_list('recipient_id', flat=True)
        )
        self.assertEqual(recipients, {self.original.pk, self.lurker.pk})
        self.assertNotIn(self.hr.pk, recipients)


class VisibilityViaSubscriptionTest(TestCase):
    """A `target_role` post must be visible to the user who created it,
    even though there's no author FK to look up. Their auto-subscription
    is what authorises them."""

    def setUp(self):
        self.author = _user('memberposter')
        self.ceo = _user('boss', role='ceo')
        self.unrelated = _user('outsider')
        self.post = Post.objects.create(content='for the boss', target_role='ceo')
        # Author auto-subscribed at post-create time. We re-create that
        # state here since we used Post.objects.create directly above.
        Subscription.objects.create(user=self.author, post=self.post)

    def test_author_sees_their_own_targeted_post(self):
        client = Client()
        client.login(username='memberposter', password='p')
        response = client.get(reverse('post_detail', args=[self.post.public_id]))
        self.assertEqual(response.status_code, 200)

    def test_target_role_sees_post(self):
        client = Client()
        client.login(username='boss', password='p')
        response = client.get(reverse('post_detail', args=[self.post.public_id]))
        self.assertEqual(response.status_code, 200)

    def test_unrelated_user_gets_403(self):
        client = Client()
        client.login(username='outsider', password='p')
        response = client.get(reverse('post_detail', args=[self.post.public_id]))
        self.assertEqual(response.status_code, 403)
