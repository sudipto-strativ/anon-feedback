from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.contrib.auth.models import User

from feedback.models import Post
from feedback.ai import (
    classify_post, apply_ai_classification, StubClassifier, AnthropicClassifier,
    GeminiClassifier, _coerce_result, VALID_LABELS,
)


def make_user(username='aiuser'):
    return User.objects.create_user(username=username, password='pass')


class CoerceResultTest(TestCase):
    def test_valid_result_normalised(self):
        out = _coerce_result({'label': 'constructive', 'mentions_individual': 1, 'toxic': 0})
        self.assertEqual(out, {
            'label': 'constructive', 'mentions_individual': True, 'toxic': False,
        })

    def test_invalid_label_raises(self):
        with self.assertRaises(ValueError):
            _coerce_result({'label': 'nonsense'})

    def test_missing_flags_default_false(self):
        out = _coerce_result({'label': 'logistics'})
        self.assertFalse(out['mentions_individual'])
        self.assertFalse(out['toxic'])


class StubClassifierTest(TestCase):
    def setUp(self):
        self.clf = StubClassifier()

    def test_profanity_is_toxic_and_attack(self):
        out = self.clf.classify("Why is the accountant so fucking rude. Get him out.")
        self.assertEqual(out['label'], 'personal_attack')
        self.assertTrue(out['toxic'])
        self.assertTrue(out['mentions_individual'])

    def test_logistics(self):
        out = self.clf.classify("Let us know the price of the car before we sell it.")
        self.assertEqual(out['label'], 'logistics')
        self.assertFalse(out['toxic'])

    def test_serious_concern(self):
        out = self.clf.classify("The owners should investigate possible financial irregularities.")
        self.assertEqual(out['label'], 'serious_concern')

    def test_constructive(self):
        out = self.clf.classify("Please ensure payslips are issued; here is my suggestion.")
        self.assertEqual(out['label'], 'constructive')

    def test_all_labels_valid(self):
        for text in ["price of the car", "fucking rude", "investigate irregularities",
                     "please ensure this", "why did we do this?", "random note"]:
            self.assertIn(self.clf.classify(text)['label'], VALID_LABELS)


@override_settings(AI_CLASSIFICATION_ENABLED=True, AI_CLASSIFIER_BACKEND='stub')
class ClassifyPostTest(TestCase):
    def test_returns_result_when_enabled(self):
        result = classify_post("Please ensure correct TDS deductions. I suggest a tax session.")
        self.assertIsNotNone(result)
        self.assertIn(result['label'], VALID_LABELS)

    def test_empty_content_returns_none(self):
        self.assertIsNone(classify_post("   "))

    def test_backend_failure_returns_none(self):
        with patch('feedback.ai.get_classifier') as mock_get:
            mock_get.return_value.classify.side_effect = RuntimeError("boom")
            self.assertIsNone(classify_post("anything"))


class ClassifyDisabledTest(TestCase):
    @override_settings(AI_CLASSIFICATION_ENABLED=False)
    def test_disabled_returns_none(self):
        self.assertIsNone(classify_post("Please ensure correct TDS deductions."))


@override_settings(AI_CLASSIFICATION_ENABLED=True, AI_CLASSIFIER_BACKEND='stub')
class ApplyClassificationTest(TestCase):
    def test_persists_label_and_flags(self):
        post = Post.objects.create(author=make_user(), content="Why is the accountant so fucking rude.")
        result = apply_ai_classification(post)
        post.refresh_from_db()
        self.assertEqual(post.ai_label, result['label'])
        self.assertEqual(post.ai_label, 'personal_attack')
        self.assertTrue(post.ai_flag_toxic)
        self.assertIsNotNone(post.ai_label_at)

    def test_noop_when_classification_returns_none(self):
        post = Post.objects.create(author=make_user('u2'), content="hello")
        with patch('feedback.ai.classify_post', return_value=None):
            self.assertIsNone(apply_ai_classification(post))
        post.refresh_from_db()
        self.assertEqual(post.ai_label, '')
        self.assertIsNone(post.ai_label_at)


@override_settings(AI_CLASSIFICATION_ENABLED=True, AI_CLASSIFIER_BACKEND='anthropic',
                   ANTHROPIC_API_KEY='test-key')
class AnthropicClassifierTest(TestCase):
    def test_parses_tool_use_block(self):
        tool_block = MagicMock()
        tool_block.type = 'tool_use'
        tool_block.name = 'record_classification'
        tool_block.input = {'label': 'serious_concern', 'mentions_individual': True, 'toxic': False}
        fake_response = MagicMock()
        fake_response.content = [tool_block]

        with patch('anthropic.Anthropic') as mock_anthropic:
            mock_anthropic.return_value.messages.create.return_value = fake_response
            clf = AnthropicClassifier()
            out = clf.classify("Investigate the office move costs.")
        self.assertEqual(out['label'], 'serious_concern')

    def test_missing_key_raises(self):
        with override_settings(ANTHROPIC_API_KEY=''):
            with self.assertRaises(RuntimeError):
                AnthropicClassifier()

    def test_full_flow_through_classify_post(self):
        tool_block = MagicMock()
        tool_block.type = 'tool_use'
        tool_block.name = 'record_classification'
        tool_block.input = {'label': 'critical_question', 'mentions_individual': False, 'toxic': False}
        fake_response = MagicMock()
        fake_response.content = [tool_block]

        with patch('anthropic.Anthropic') as mock_anthropic:
            mock_anthropic.return_value.messages.create.return_value = fake_response
            result = classify_post("How much value did the layoff add?")
        self.assertEqual(result['label'], 'critical_question')


@override_settings(AI_CLASSIFICATION_ENABLED=True, AI_CLASSIFIER_BACKEND='gemini',
                   GEMINI_API_KEY='test-key')
class GeminiClassifierTest(TestCase):
    def _fake_response(self, payload):
        fake = MagicMock()
        fake.text = payload
        return fake

    def test_parses_json_response(self):
        fake = self._fake_response(
            '{"label": "serious_concern", "mentions_individual": true, "toxic": false}'
        )
        with patch('google.genai.Client') as mock_client:
            mock_client.return_value.models.generate_content.return_value = fake
            clf = GeminiClassifier()
            out = clf.classify("Investigate the office move costs.")
        self.assertEqual(out['label'], 'serious_concern')
        self.assertTrue(out['mentions_individual'])

    def test_missing_key_raises(self):
        with override_settings(GEMINI_API_KEY=''):
            with self.assertRaises(RuntimeError):
                GeminiClassifier()

    def test_empty_text_raises(self):
        with patch('google.genai.Client') as mock_client:
            mock_client.return_value.models.generate_content.return_value = self._fake_response('')
            clf = GeminiClassifier()
            with self.assertRaises(ValueError):
                clf.classify("anything")

    def test_full_flow_through_classify_post(self):
        fake = self._fake_response(
            '{"label": "critical_question", "mentions_individual": false, "toxic": false}'
        )
        with patch('google.genai.Client') as mock_client:
            mock_client.return_value.models.generate_content.return_value = fake
            result = classify_post("How much value did the layoff add?")
        self.assertEqual(result['label'], 'critical_question')

    def test_bad_label_coerced_to_none(self):
        fake = self._fake_response('{"label": "nonsense", "mentions_individual": false, "toxic": false}')
        with patch('google.genai.Client') as mock_client:
            mock_client.return_value.models.generate_content.return_value = fake
            # invalid label fails validation in classify_post -> None (never breaks post)
            self.assertIsNone(classify_post("something"))
