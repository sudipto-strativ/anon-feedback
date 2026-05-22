"""Hard tripwires for the anonymity hardening (migration 0012).

These tests verify the structural promise: there is no way to ask the
ORM "who wrote this post?" because the FK doesn't exist any more.
If anyone re-introduces it (an `author = ForeignKey(User)` slipping
back into Post or Comment), these tests fail loudly.
"""

from django.contrib.auth.models import User
from django.test import TestCase

from feedback.models import Comment, Post, Subscription


class PostHasNoAuthorFieldTest(TestCase):
    def test_post_model_has_no_author_field(self):
        names = {f.name for f in Post._meta.get_fields()}
        self.assertNotIn(
            'author', names,
            "Post.author must not exist — see migration 0012 / "
            "docs/anonymity rationale.",
        )

    def test_post_does_not_accept_author_kwarg(self):
        with self.assertRaises(TypeError):
            Post(author=User.objects.create_user('x', password='p'))


class CommentHasNoAuthorFieldTest(TestCase):
    def test_comment_model_has_no_author_field(self):
        names = {f.name for f in Comment._meta.get_fields()}
        self.assertNotIn('author', names)

    def test_comment_has_role_snapshot_instead(self):
        user = User.objects.create_user('alice', password='p')
        user.profile.role = 'hr'
        user.profile.save()
        post = Post.objects.create(content='hello')
        comment = Comment.objects.create(post=post, role='hr', content='hi')
        self.assertEqual(comment.role, 'hr')
        # No back-reference to the User on the comment.
        self.assertFalse(hasattr(comment, 'author'))


class PostPublicIdIsUuidTest(TestCase):
    def test_public_id_is_unique_uuid_per_post(self):
        p1 = Post.objects.create(content='a')
        p2 = Post.objects.create(content='b')
        self.assertNotEqual(p1.public_id, p2.public_id)
        # UUIDs are 36 chars in hyphenated form.
        self.assertEqual(len(str(p1.public_id)), 36)

    def test_public_id_default_is_callable(self):
        # Two posts created in the same migration tick must still get
        # distinct UUIDs. (Catches mistakes where the default is
        # `uuid.uuid4()` instead of `uuid.uuid4`.)
        posts = [Post.objects.create(content=str(i)) for i in range(5)]
        ids = {p.public_id for p in posts}
        self.assertEqual(len(ids), 5)


class SubscriptionIsTheNewRoutingTableTest(TestCase):
    def test_subscription_uniqueness_per_user_post_pair(self):
        from django.db import IntegrityError
        user = User.objects.create_user('a', password='p')
        post = Post.objects.create(content='x')
        Subscription.objects.create(user=user, post=post)
        with self.assertRaises(IntegrityError):
            Subscription.objects.create(user=user, post=post)

    def test_subscription_has_no_created_at(self):
        """Intentional. Ordering by creation would leak who got there
        first (≈ the author). See model docstring."""
        names = {f.name for f in Subscription._meta.get_fields()}
        self.assertNotIn('created_at', names)
