from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User

from feedback.templatetags.feedback_extras import (
    timesince_short, truncate_chars, get_item, score_class,
    render_markdown, avatar_gradient, user_role_badge,
    AVATAR_GRADIENTS,
)


def make_user(username='testuser', role='employee'):
    user = User.objects.create_user(username=username, password='pass')
    user.profile.role = role
    user.profile.save()
    return user


class TimeSinceShortFilterTest(TestCase):
    def _ago(self, **kwargs):
        return timezone.now() - timedelta(**kwargs)

    def test_empty_value(self):
        self.assertEqual(timesince_short(None), '')

    def test_just_now(self):
        self.assertEqual(timesince_short(self._ago(seconds=30)), 'just now')

    def test_minutes(self):
        result = timesince_short(self._ago(minutes=5))
        self.assertEqual(result, '5m ago')

    def test_hours(self):
        result = timesince_short(self._ago(hours=3))
        self.assertEqual(result, '3h ago')

    def test_days(self):
        result = timesince_short(self._ago(days=2))
        self.assertEqual(result, '2d ago')

    def test_weeks(self):
        result = timesince_short(self._ago(days=14))
        self.assertEqual(result, '2w ago')

    def test_months(self):
        result = timesince_short(self._ago(days=60))
        self.assertEqual(result, '2mo ago')

    def test_years(self):
        result = timesince_short(self._ago(days=730))
        self.assertEqual(result, '2y ago')

    def test_boundary_just_now_59_seconds(self):
        result = timesince_short(self._ago(seconds=59))
        self.assertEqual(result, 'just now')

    def test_boundary_1_minute(self):
        result = timesince_short(self._ago(seconds=60))
        self.assertEqual(result, '1m ago')


class TruncateCharsFilterTest(TestCase):
    def test_short_string_unchanged(self):
        self.assertEqual(truncate_chars('Hello', 10), 'Hello')

    def test_exact_length_unchanged(self):
        self.assertEqual(truncate_chars('Hello', 5), 'Hello')

    def test_long_string_truncated(self):
        result = truncate_chars('Hello World', 5)
        self.assertTrue(result.endswith('...'))
        self.assertLessEqual(len(result), 8)

    def test_empty_string(self):
        self.assertEqual(truncate_chars('', 10), '')

    def test_none_returns_empty(self):
        self.assertEqual(truncate_chars(None, 10), '')

    def test_trailing_space_stripped_before_ellipsis(self):
        result = truncate_chars('Hello World', 6)
        self.assertFalse(result.startswith('Hello '))


class GetItemFilterTest(TestCase):
    def test_existing_key(self):
        self.assertEqual(get_item({'a': 1}, 'a'), 1)

    def test_missing_key(self):
        self.assertIsNone(get_item({'a': 1}, 'b'))

    def test_empty_dict(self):
        self.assertIsNone(get_item({}, 'key'))

    def test_none_dict(self):
        self.assertIsNone(get_item(None, 'key'))

    def test_integer_key(self):
        self.assertEqual(get_item({1: 'val'}, 1), 'val')


class ScoreClassFilterTest(TestCase):
    def test_positive_score(self):
        self.assertEqual(score_class(5), 'positive')

    def test_negative_score(self):
        self.assertEqual(score_class(-3), 'negative')

    def test_zero_score(self):
        self.assertEqual(score_class(0), 'neutral')

    def test_string_score(self):
        self.assertEqual(score_class('10'), 'positive')

    def test_invalid_value(self):
        self.assertEqual(score_class('abc'), 'neutral')

    def test_none(self):
        self.assertEqual(score_class(None), 'neutral')


class RenderMarkdownFilterTest(TestCase):
    def test_empty_string(self):
        self.assertEqual(render_markdown(''), '')

    def test_none(self):
        self.assertEqual(render_markdown(None), '')

    def test_bold_text(self):
        result = render_markdown('**bold**')
        self.assertIn('<strong>bold</strong>', result)

    def test_italic_text(self):
        result = render_markdown('_italic_')
        self.assertIn('<em>italic</em>', result)

    def test_link_preserved(self):
        result = render_markdown('[link](https://example.com)')
        self.assertIn('href', result)

    def test_script_tag_stripped(self):
        result = render_markdown('<script>alert("xss")</script>')
        self.assertNotIn('<script>', result)

    def test_fenced_code_block(self):
        result = render_markdown('```python\nprint("hi")\n```')
        self.assertIn('<code', result)

    def test_table_rendered(self):
        md = '| a | b |\n|---|---|\n| 1 | 2 |'
        result = render_markdown(md)
        self.assertIn('<table>', result)


class AvatarGradientFilterTest(TestCase):
    def test_returns_gradient_string(self):
        result = avatar_gradient(1)
        self.assertIn('linear-gradient', result)

    def test_deterministic(self):
        self.assertEqual(avatar_gradient(3), avatar_gradient(3))

    def test_wraps_around(self):
        n = len(AVATAR_GRADIENTS)
        self.assertEqual(avatar_gradient(0), avatar_gradient(n))

    def test_invalid_returns_first(self):
        self.assertEqual(avatar_gradient(None), AVATAR_GRADIENTS[0])

    def test_all_ids_return_valid_gradient(self):
        for i in range(20):
            result = avatar_gradient(i)
            self.assertIn('linear-gradient', result)


class UserRoleBadgeTagTest(TestCase):
    def test_employee_badge(self):
        user = make_user('alice', 'employee')
        result = user_role_badge(user)
        self.assertIn('role-badge-employee', result)
        self.assertIn('Member', result)

    def test_hr_badge(self):
        user = make_user('alice', 'hr')
        result = user_role_badge(user)
        self.assertIn('role-badge-hr', result)
        self.assertIn('HR', result)

    def test_ceo_badge(self):
        user = make_user('alice', 'ceo')
        result = user_role_badge(user)
        self.assertIn('role-badge-ceo', result)
        self.assertIn('CEO', result)

    def test_user_without_profile(self):
        user = User(username='noprofile')
        result = user_role_badge(user)
        self.assertIn('role-badge-employee', result)
