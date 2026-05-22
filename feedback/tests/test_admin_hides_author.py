"""Admin panel can no longer expose authorship.

The admin module changes in feedback/admin.py are themselves the
implementation. These tests check we don't regress:

- PostAdmin and CommentAdmin must not declare any author column,
  search field, or filter that joins on User.
- Vote / Favourite / Subscription / User admin must refuse access to
  non-superuser staff.
"""

from django.contrib.admin.sites import site
from django.contrib.auth.models import User
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from feedback.admin import (
    CommentAdmin,
    PostAdmin,
    SubscriptionAdmin,
    VoteAdmin,
)
from feedback.models import Comment, Post, Subscription, Vote


class _AnyRequest:
    """Tiny stand-in for a real request — `_SuperuserOnlyMixin` only
    looks at `request.user`."""
    def __init__(self, user):
        self.user = user


class AdminHidesAuthorColumnsTest(TestCase):
    def test_post_admin_does_not_reference_author_anywhere(self):
        ma = PostAdmin(Post, site)
        joined = ' '.join(map(str, ma.list_display + ma.list_filter + ma.search_fields))
        self.assertNotIn('author', joined.lower())

    def test_comment_admin_does_not_reference_author(self):
        ma = CommentAdmin(Comment, site)
        joined = ' '.join(map(str, ma.list_display + ma.list_filter + ma.search_fields))
        self.assertNotIn('author', joined.lower())


class AdminGatesUserLinkedModelsToSuperuserTest(TestCase):
    def setUp(self):
        self.regular_staff = User.objects.create_user(
            'staffuser', password='p', is_staff=True
        )
        self.super = User.objects.create_user(
            'rootuser', password='p', is_staff=True, is_superuser=True
        )

    def _assertions_for(self, admin_class, model):
        ma = admin_class(model, site)
        request = _AnyRequest(self.regular_staff)
        self.assertFalse(ma.has_view_permission(request))
        self.assertFalse(ma.has_change_permission(request))
        self.assertFalse(ma.has_module_permission(request))

        super_request = _AnyRequest(self.super)
        self.assertTrue(ma.has_view_permission(super_request))
        self.assertTrue(ma.has_module_permission(super_request))

    def test_vote_admin_is_superuser_only(self):
        self._assertions_for(VoteAdmin, Vote)

    def test_subscription_admin_is_superuser_only(self):
        self._assertions_for(SubscriptionAdmin, Subscription)


class AdminURLsRejectStaffTest(TestCase):
    """Black-box check: a non-superuser staff user hitting the Vote
    admin gets a 403/302, not a list of who voted on what."""

    def setUp(self):
        self.client = Client()
        self.regular_staff = User.objects.create_user(
            'staffuser', password='p', is_staff=True
        )
        self.client.login(username='staffuser', password='p')

    def test_vote_changelist_denied(self):
        url = reverse('admin:feedback_vote_changelist')
        response = self.client.get(url)
        # Non-superuser staff should be redirected or refused.
        self.assertIn(response.status_code, (302, 403))

    def test_subscription_changelist_denied(self):
        url = reverse('admin:feedback_subscription_changelist')
        response = self.client.get(url)
        self.assertIn(response.status_code, (302, 403))
