from django.test import TestCase
from django.contrib.auth.models import User
from django.db import IntegrityError

from feedback.models import (
    UserProfile, NotificationEmail, SlackConfig,
    Post, Comment, Favourite, PostAttachment, CommentImage, Vote,
)


def make_user(username='testuser', **kwargs):
    return User.objects.create_user(username=username, password='pass', **kwargs)


def make_post(author, content='Test content', status='pending'):
    return Post.objects.create(author=author, content=content, status=status)


class UserProfileModelTest(TestCase):
    def setUp(self):
        self.user = make_user('alice')
        self.profile = self.user.profile  # auto-created by signal

    def test_str(self):
        self.assertEqual(str(self.profile), 'alice (employee)')

    def test_default_role(self):
        self.assertEqual(self.profile.role, 'employee')

    def test_role_display_employee(self):
        self.assertEqual(self.profile.role_display, 'Member')

    def test_role_display_hr(self):
        self.profile.role = 'hr'
        self.assertEqual(self.profile.role_display, 'HR')

    def test_role_display_ceo(self):
        self.profile.role = 'ceo'
        self.assertEqual(self.profile.role_display, 'CEO')

    def test_role_display_unknown(self):
        self.profile.role = 'unknown'
        self.assertEqual(self.profile.role_display, 'Member')


class NotificationEmailModelTest(TestCase):
    def test_str(self):
        email = NotificationEmail.objects.create(email='admin@example.com')
        self.assertEqual(str(email), 'admin@example.com')

    def test_defaults(self):
        email = NotificationEmail.objects.create(email='x@example.com')
        self.assertTrue(email.notify_on_new_post)
        self.assertTrue(email.notify_on_new_comment)

    def test_email_unique(self):
        NotificationEmail.objects.create(email='dup@example.com')
        with self.assertRaises(IntegrityError):
            NotificationEmail.objects.create(email='dup@example.com')


class SlackConfigModelTest(TestCase):
    def test_str_with_channel(self):
        cfg = SlackConfig.objects.create(webhook_url='https://hooks.slack.com/x', channel_name='#general')
        self.assertEqual(str(cfg), 'Slack: #general')

    def test_str_without_channel(self):
        cfg = SlackConfig.objects.create(webhook_url='https://hooks.slack.com/x')
        self.assertEqual(str(cfg), 'Slack: https://hooks.slack.com/x')

    def test_default_active(self):
        cfg = SlackConfig.objects.create(webhook_url='https://hooks.slack.com/x')
        self.assertTrue(cfg.is_active)


class PostModelTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.post = make_post(self.user, 'Hello world')

    def test_str(self):
        self.assertIn('testuser', str(self.post))

    def test_default_status(self):
        self.assertEqual(self.post.status, 'pending')

    def test_like_count_zero(self):
        self.assertEqual(self.post.like_count, 0)

    def test_dislike_count_zero(self):
        self.assertEqual(self.post.dislike_count, 0)

    def test_score_zero(self):
        self.assertEqual(self.post.score, 0)

    def test_like_count_with_votes(self):
        other = make_user('other')
        Vote.objects.create(user=self.user, post=self.post, vote_type='like')
        Vote.objects.create(user=other, post=self.post, vote_type='like')
        self.assertEqual(self.post.like_count, 2)

    def test_dislike_count_with_votes(self):
        Vote.objects.create(user=self.user, post=self.post, vote_type='dislike')
        self.assertEqual(self.post.dislike_count, 1)

    def test_score_mixed_votes(self):
        other = make_user('other')
        Vote.objects.create(user=self.user, post=self.post, vote_type='like')
        Vote.objects.create(user=other, post=self.post, vote_type='dislike')
        self.assertEqual(self.post.score, 0)

    def test_comment_count(self):
        self.assertEqual(self.post.comment_count, 0)
        Comment.objects.create(post=self.post, author=self.user, content='hi')
        self.assertEqual(self.post.comment_count, 1)

    def test_get_status_color_pending(self):
        self.assertEqual(self.post.get_status_color(), 'warning')

    def test_get_status_color_in_progress(self):
        self.post.status = 'in_progress'
        self.assertEqual(self.post.get_status_color(), 'primary')

    def test_get_status_color_done(self):
        self.post.status = 'done'
        self.assertEqual(self.post.get_status_color(), 'success')

    def test_get_status_color_rejected(self):
        self.post.status = 'rejected'
        self.assertEqual(self.post.get_status_color(), 'danger')

    def test_get_status_color_unknown(self):
        self.post.status = 'mystery'
        self.assertEqual(self.post.get_status_color(), 'secondary')

    def test_ordering_newest_first(self):
        other = make_user('other')
        post2 = make_post(other, 'Second post')
        posts = list(Post.objects.all())
        self.assertEqual(posts[0].id, post2.id)
        self.assertEqual(posts[1].id, self.post.id)


class CommentModelTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.post = make_post(self.user)
        self.comment = Comment.objects.create(post=self.post, author=self.user, content='Nice post')

    def test_str(self):
        self.assertIn('testuser', str(self.comment))
        self.assertIn(str(self.post.id), str(self.comment))

    def test_like_count_zero(self):
        self.assertEqual(self.comment.like_count, 0)

    def test_dislike_count_zero(self):
        self.assertEqual(self.comment.dislike_count, 0)

    def test_score_zero(self):
        self.assertEqual(self.comment.score, 0)

    def test_like_count_with_vote(self):
        Vote.objects.create(user=self.user, comment=self.comment, vote_type='like')
        self.assertEqual(self.comment.like_count, 1)

    def test_score_with_votes(self):
        other = make_user('other')
        Vote.objects.create(user=self.user, comment=self.comment, vote_type='like')
        Vote.objects.create(user=other, comment=self.comment, vote_type='like')
        self.assertEqual(self.comment.score, 2)

    def test_ordering_oldest_first(self):
        other = make_user('other')
        comment2 = Comment.objects.create(post=self.post, author=other, content='reply')
        comments = list(Comment.objects.filter(post=self.post))
        self.assertEqual(comments[0].id, self.comment.id)
        self.assertEqual(comments[1].id, comment2.id)


class FavouriteModelTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.post = make_post(self.user)

    def test_str(self):
        fav = Favourite.objects.create(user=self.user, post=self.post)
        self.assertIn(self.user.username, str(fav))
        self.assertIn(str(self.post.id), str(fav))

    def test_unique_constraint(self):
        Favourite.objects.create(user=self.user, post=self.post)
        with self.assertRaises(IntegrityError):
            Favourite.objects.create(user=self.user, post=self.post)


class PostAttachmentModelTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.post = make_post(self.user)

    def _make_attachment(self, path):
        return PostAttachment(post=self.post, file=path)

    def test_filename(self):
        att = self._make_attachment('post_attachments/2024/01/report.pdf')
        self.assertEqual(att.filename, 'report.pdf')

    def test_extension_pdf(self):
        att = self._make_attachment('post_attachments/2024/01/report.pdf')
        self.assertEqual(att.extension, '.pdf')

    def test_extension_uppercase_normalized(self):
        att = self._make_attachment('post_attachments/2024/01/photo.JPG')
        self.assertEqual(att.extension, '.jpg')

    def test_is_image_true(self):
        for ext in ('photo.jpg', 'photo.jpeg', 'photo.png', 'photo.gif', 'photo.webp'):
            att = self._make_attachment(f'post_attachments/2024/01/{ext}')
            self.assertTrue(att.is_image, f'{ext} should be image')

    def test_is_image_false(self):
        for ext in ('doc.pdf', 'doc.docx', 'sheet.xlsx', 'data.csv'):
            att = self._make_attachment(f'post_attachments/2024/01/{ext}')
            self.assertFalse(att.is_image, f'{ext} should not be image')

    def test_icon_class_pdf(self):
        att = self._make_attachment('x.pdf')
        self.assertEqual(att.icon_class, 'bi-file-pdf-fill')

    def test_icon_class_word(self):
        self.assertEqual(self._make_attachment('x.doc').icon_class, 'bi-file-word-fill')
        self.assertEqual(self._make_attachment('x.docx').icon_class, 'bi-file-word-fill')

    def test_icon_class_excel(self):
        self.assertEqual(self._make_attachment('x.xls').icon_class, 'bi-file-excel-fill')
        self.assertEqual(self._make_attachment('x.xlsx').icon_class, 'bi-file-excel-fill')

    def test_icon_class_csv(self):
        self.assertEqual(self._make_attachment('x.csv').icon_class, 'bi-file-spreadsheet-fill')

    def test_icon_class_default(self):
        self.assertEqual(self._make_attachment('x.zip').icon_class, 'bi-file-earmark-fill')

    def test_icon_color_pdf(self):
        self.assertEqual(self._make_attachment('x.pdf').icon_color, '#ef4444')

    def test_icon_color_word(self):
        self.assertEqual(self._make_attachment('x.docx').icon_color, '#2563eb')

    def test_icon_color_excel(self):
        self.assertEqual(self._make_attachment('x.xlsx').icon_color, '#16a34a')

    def test_icon_color_csv(self):
        self.assertEqual(self._make_attachment('x.csv').icon_color, '#16a34a')

    def test_icon_color_default(self):
        self.assertEqual(self._make_attachment('x.zip').icon_color, '#6366f1')

    def test_str(self):
        att = PostAttachment.objects.create(post=self.post, file='post_attachments/2024/01/test.pdf')
        self.assertIn(str(self.post.id), str(att))
        self.assertIn('test.pdf', str(att))


class CommentImageModelTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.post = make_post(self.user)
        self.comment = Comment.objects.create(post=self.post, author=self.user, content='hi')

    def test_str(self):
        img = CommentImage(comment=self.comment, image='comment_images/2024/01/img.jpg')
        self.assertIn(str(self.comment.id), str(img))


class VoteModelTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.other = make_user('other')
        self.post = make_post(self.user)
        self.comment = Comment.objects.create(post=self.post, author=self.user, content='hi')

    def test_unique_post_vote(self):
        Vote.objects.create(user=self.user, post=self.post, vote_type='like')
        with self.assertRaises(IntegrityError):
            Vote.objects.create(user=self.user, post=self.post, vote_type='dislike')

    def test_unique_comment_vote(self):
        Vote.objects.create(user=self.user, comment=self.comment, vote_type='like')
        with self.assertRaises(IntegrityError):
            Vote.objects.create(user=self.user, comment=self.comment, vote_type='dislike')

    def test_different_users_can_vote_same_post(self):
        Vote.objects.create(user=self.user, post=self.post, vote_type='like')
        Vote.objects.create(user=self.other, post=self.post, vote_type='like')
        self.assertEqual(Vote.objects.filter(post=self.post).count(), 2)

    def test_same_user_can_vote_post_and_comment(self):
        Vote.objects.create(user=self.user, post=self.post, vote_type='like')
        Vote.objects.create(user=self.user, comment=self.comment, vote_type='dislike')
        self.assertEqual(Vote.objects.filter(user=self.user).count(), 2)
