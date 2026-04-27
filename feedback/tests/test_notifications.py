from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.contrib.auth.models import User

from feedback.models import Post, Comment, NotificationEmail, SlackConfig
from feedback.notifications import (
    send_slack_message, notify_new_post, notify_new_comment, notify_status_update,
)


def make_user(username='testuser'):
    return User.objects.create_user(username=username, password='pass')


def make_post(author, content='Test content', status='pending'):
    return Post.objects.create(author=author, content=content, status=status)


class SendSlackMessageTest(TestCase):
    def test_no_config_no_settings_does_nothing(self):
        """No SlackConfig and no SLACK_WEBHOOK_URL — silently returns."""
        with patch('feedback.notifications.requests.post') as mock_post:
            send_slack_message('hello')
        mock_post.assert_not_called()

    @override_settings(SLACK_WEBHOOK_URL='https://hooks.slack.com/fallback')
    def test_settings_fallback_used_when_no_config(self):
        with patch('feedback.notifications.requests.post') as mock_post:
            send_slack_message('hello')
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], 'https://hooks.slack.com/fallback')

    def test_uses_slack_config_webhook(self):
        SlackConfig.objects.create(webhook_url='https://hooks.slack.com/config', is_active=True)
        with patch('feedback.notifications.requests.post') as mock_post:
            send_slack_message('hello')
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], 'https://hooks.slack.com/config')

    def test_uses_channel_from_config(self):
        SlackConfig.objects.create(
            webhook_url='https://hooks.slack.com/x',
            channel_name='#feedback',
            is_active=True,
        )
        with patch('feedback.notifications.requests.post') as mock_post:
            send_slack_message('hello')
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['channel'], '#feedback')

    def test_inactive_config_not_used(self):
        SlackConfig.objects.create(webhook_url='https://hooks.slack.com/inactive', is_active=False)
        with patch('feedback.notifications.requests.post') as mock_post:
            send_slack_message('hello')
        mock_post.assert_not_called()

    def test_request_error_logged_not_raised(self):
        SlackConfig.objects.create(webhook_url='https://hooks.slack.com/x', is_active=True)
        with patch('feedback.notifications.requests.post', side_effect=Exception('timeout')):
            # Should not raise
            send_slack_message('hello')


class NotifyNewPostTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.post = make_post(self.user, 'Feedback content here')

    @patch('feedback.notifications.send_slack_message')
    @patch('feedback.notifications.send_mail')
    def test_slack_called(self, mock_mail, mock_slack):
        notify_new_post(self.post)
        mock_slack.assert_called_once()

    @patch('feedback.notifications.send_slack_message')
    @patch('feedback.notifications.send_mail')
    def test_slack_message_contains_post_content(self, mock_mail, mock_slack):
        notify_new_post(self.post)
        message = mock_slack.call_args[0][0]
        self.assertIn('Feedback content here', message)

    @patch('feedback.notifications.send_slack_message')
    @patch('feedback.notifications.send_mail')
    def test_email_sent_to_subscribers(self, mock_mail, mock_slack):
        NotificationEmail.objects.create(email='admin@example.com', notify_on_new_post=True)
        notify_new_post(self.post)
        mock_mail.assert_called_once()
        _, kwargs = mock_mail.call_args
        self.assertIn('admin@example.com', kwargs['recipient_list'])

    @patch('feedback.notifications.send_slack_message')
    @patch('feedback.notifications.send_mail')
    def test_no_email_if_no_subscribers(self, mock_mail, mock_slack):
        notify_new_post(self.post)
        mock_mail.assert_not_called()

    @override_settings(EMAIL_NOTIFICATION_ENABLED=False)
    @patch('feedback.notifications.send_slack_message')
    @patch('feedback.notifications.send_mail')
    def test_email_disabled_by_setting(self, mock_mail, mock_slack):
        NotificationEmail.objects.create(email='admin@example.com', notify_on_new_post=True)
        notify_new_post(self.post)
        mock_mail.assert_not_called()

    @patch('feedback.notifications.send_slack_message')
    @patch('feedback.notifications.send_mail')
    def test_post_opt_out_subscribers_not_emailed(self, mock_mail, mock_slack):
        NotificationEmail.objects.create(email='optout@example.com', notify_on_new_post=False)
        notify_new_post(self.post)
        mock_mail.assert_not_called()

    @patch('feedback.notifications.send_slack_message')
    @patch('feedback.notifications.send_mail')
    def test_long_content_truncated_in_slack(self, mock_mail, mock_slack):
        self.post.content = 'x' * 300
        self.post.save()
        notify_new_post(self.post)
        message = mock_slack.call_args[0][0]
        # Should contain at most 200 chars of content
        self.assertIn('x' * 200, message)
        self.assertNotIn('x' * 201, message)


class NotifyNewCommentTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.post = make_post(self.user)
        self.comment = Comment.objects.create(
            post=self.post, author=self.user, content='Great idea!'
        )

    @patch('feedback.notifications.send_slack_message')
    @patch('feedback.notifications.send_mail')
    def test_slack_called(self, mock_mail, mock_slack):
        notify_new_comment(self.comment)
        mock_slack.assert_called_once()

    @patch('feedback.notifications.send_slack_message')
    @patch('feedback.notifications.send_mail')
    def test_slack_message_contains_comment_content(self, mock_mail, mock_slack):
        notify_new_comment(self.comment)
        message = mock_slack.call_args[0][0]
        self.assertIn('Great idea!', message)

    @patch('feedback.notifications.send_slack_message')
    @patch('feedback.notifications.send_mail')
    def test_email_sent_to_comment_subscribers(self, mock_mail, mock_slack):
        NotificationEmail.objects.create(email='admin@example.com', notify_on_new_comment=True)
        notify_new_comment(self.comment)
        mock_mail.assert_called_once()

    @patch('feedback.notifications.send_slack_message')
    @patch('feedback.notifications.send_mail')
    def test_comment_opt_out_not_emailed(self, mock_mail, mock_slack):
        NotificationEmail.objects.create(email='x@example.com', notify_on_new_comment=False)
        notify_new_comment(self.comment)
        mock_mail.assert_not_called()

    @patch('feedback.notifications.send_slack_message')
    @patch('feedback.notifications.send_mail')
    def test_role_display_in_slack_message(self, mock_mail, mock_slack):
        self.user.profile.role = 'hr'
        self.user.profile.save()
        notify_new_comment(self.comment)
        message = mock_slack.call_args[0][0]
        self.assertIn('HR', message)


class NotifyStatusUpdateTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.updater = make_user('updater')
        self.post = make_post(self.user, 'Some feedback')

    @patch('feedback.notifications.send_slack_message')
    def test_slack_called(self, mock_slack):
        notify_status_update(self.post, self.updater)
        mock_slack.assert_called_once()

    @patch('feedback.notifications.send_slack_message')
    def test_message_contains_status(self, mock_slack):
        self.post.status = 'done'
        self.post.remark = 'Fixed!'
        notify_status_update(self.post, self.updater)
        message = mock_slack.call_args[0][0]
        self.assertIn('Done', message)

    @patch('feedback.notifications.send_slack_message')
    def test_message_contains_eta_when_set(self, mock_slack):
        from datetime import date
        self.post.eta = date(2025, 12, 31)
        notify_status_update(self.post, self.updater)
        message = mock_slack.call_args[0][0]
        self.assertIn('ETA', message)

    @patch('feedback.notifications.send_slack_message')
    def test_done_uses_remark_in_preview(self, mock_slack):
        self.post.status = 'done'
        self.post.remark = 'All resolved!'
        notify_status_update(self.post, self.updater)
        message = mock_slack.call_args[0][0]
        self.assertIn('All resolved!', message)

    @patch('feedback.notifications.send_slack_message')
    def test_pending_uses_content_in_preview(self, mock_slack):
        notify_status_update(self.post, self.updater)
        message = mock_slack.call_args[0][0]
        self.assertIn('Some feedback', message)
