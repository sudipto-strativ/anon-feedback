"""AI classification of feedback posts.

A post is classified along one public label plus two moderation flags:

    label: one of Post.AI_LABEL_CHOICES
    mentions_individual: names a specific (non-executive) person
    toxic: profanity or personal abuse

The public entry point is ``classify_post(content)`` which returns a dict
``{'label', 'mentions_individual', 'toxic'}`` or ``None`` on any failure.

The actual work is delegated to a *classifier backend* chosen by the
``AI_CLASSIFIER_BACKEND`` setting:

    'stub'      -> StubClassifier    (deterministic heuristics, no API key)
    'anthropic' -> AnthropicClassifier (Claude Haiku, needs ANTHROPIC_API_KEY)

This keeps the whole post-creation flow testable without a key: the stub is
the default, and the real call drops in behind the same ``classify`` interface.

Classification is a best-effort side effect — callers must treat ``None`` as
"not classified" and never let it block post creation. Only the post *content*
is ever sent to an external API; author identity is never included (posts are
anonymous).
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

VALID_LABELS = {choice[0] for choice in (
    ('constructive', ''),
    ('critical_question', ''),
    ('serious_concern', ''),
    ('personal_attack', ''),
    ('logistics', ''),
)}

LABEL_GUIDE = """\
- constructive: raises a problem AND offers a concrete suggestion, request, or path forward.
  e.g. "Please issue monthly payslips and run a written tax session so people understand deductions."
- critical_question: challenges or questions a decision with reasoning, but is not abusive. It may
  name a person as long as the tone stays respectful.
  e.g. "Why did we let the HR person go? She responded fast and could have improved with support."
- serious_concern: alleges unfairness, wrongdoing, or financial/ethical irregularity that warrants review.
  e.g. "The owners should investigate the office-move costs; there may be financial irregularities."
- personal_attack: hostile and aimed at a specific individual; insulting or demanding they be removed.
  e.g. "Why is the accountant so rude, get him out, he treats staff like slaves."
- logistics: administrative, marketplace, or off-topic housekeeping with no workplace feedback content.
  e.g. "Let us know the price of the car before we sell it to someone else."
"""

SYSTEM_PROMPT = (
    "You classify anonymous workplace feedback posts. "
    "Assign exactly one label and two boolean flags.\n\n"
    "Labels (choose the single best fit):\n" + LABEL_GUIDE + "\n"
    "Flags:\n"
    "- mentions_individual: true if the post names or clearly identifies a specific "
    "non-executive person (by name, role held by one identifiable person, etc.).\n"
    "- toxic: true if the post contains profanity, slurs, or personal abuse.\n\n"
    "Judge only the text. Do not infer who wrote it. Return only the structured classification."
)


def _coerce_result(raw):
    """Validate a raw backend dict into a clean result or raise ValueError."""
    label = (raw or {}).get('label')
    if label not in VALID_LABELS:
        raise ValueError(f"invalid label: {label!r}")
    return {
        'label': label,
        'mentions_individual': bool((raw or {}).get('mentions_individual', False)),
        'toxic': bool((raw or {}).get('toxic', False)),
    }


class StubClassifier:
    """Deterministic, keyword-based classifier used when no API key is wired.

    Not meant to be accurate — it makes the end-to-end flow demonstrable and
    gives tests something stable to assert against.
    """

    PROFANITY = ('fuck', 'fucking', 'shit', 'wtf', 'bastard', 'asshole')
    ATTACK_HINTS = ('get him out', 'get her out', 'so rude', 'mistakes/day', 'ego')
    CONCERN_HINTS = ('investigat', 'irregularit', 'favoritism', 'favouritism',
                     'unfair', 'secret', 'misuse', 'fraud')
    CONSTRUCTIVE_HINTS = ('please ensure', 'suggest', 'propose', 'we should',
                          'can we all', 'solution', 'request')
    LOGISTICS_HINTS = ('for sale', 'price of the', 'selling', 'buy it', 'interested in buying')

    def classify(self, content):
        text = (content or '').lower()

        toxic = any(word in text for word in self.PROFANITY)
        attackish = toxic or any(h in text for h in self.ATTACK_HINTS)

        if any(h in text for h in self.LOGISTICS_HINTS):
            label = 'logistics'
        elif attackish:
            label = 'personal_attack'
        elif any(h in text for h in self.CONCERN_HINTS):
            label = 'serious_concern'
        elif any(h in text for h in self.CONSTRUCTIVE_HINTS):
            label = 'constructive'
        elif '?' in text:
            label = 'critical_question'
        else:
            label = 'constructive'

        # Heuristic for naming an individual: a capitalised first name near a
        # judgemental verb is too fragile, so the stub flags only on attack cues.
        mentions_individual = attackish or label == 'personal_attack'

        return {
            'label': label,
            'mentions_individual': mentions_individual,
            'toxic': toxic,
        }


class AnthropicClassifier:
    """Classifier backed by Claude Haiku via the Anthropic API."""

    MODEL = 'claude-haiku-4-5'
    TOOL = {
        'name': 'record_classification',
        'description': 'Record the classification of the feedback post.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'label': {
                    'type': 'string',
                    'enum': sorted(VALID_LABELS),
                    'description': 'The single best-fit label for the post.',
                },
                'mentions_individual': {
                    'type': 'boolean',
                    'description': 'Whether the post names a specific non-executive individual.',
                },
                'toxic': {
                    'type': 'boolean',
                    'description': 'Whether the post contains profanity or personal abuse.',
                },
            },
            'required': ['label', 'mentions_individual', 'toxic'],
        },
    }

    def __init__(self):
        import anthropic  # imported lazily so the dep is optional for stub users
        api_key = getattr(settings, 'ANTHROPIC_API_KEY', '')
        if not api_key:
            raise RuntimeError('ANTHROPIC_API_KEY is not configured')
        self._client = anthropic.Anthropic(api_key=api_key)

    def classify(self, content):
        response = self._client.messages.create(
            model=self.MODEL,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            tools=[self.TOOL],
            tool_choice={'type': 'tool', 'name': self.TOOL['name']},
            messages=[{'role': 'user', 'content': content}],
        )
        for block in response.content:
            if getattr(block, 'type', None) == 'tool_use' and block.name == self.TOOL['name']:
                return block.input
        raise ValueError('model did not return a classification tool call')


class GeminiClassifier:
    """Classifier backed by Google Gemini Flash via the google-genai SDK.

    Gemini's API has a free tier (Google AI Studio), so this backend can run
    the feature at no cost for low-volume boards. Uses structured JSON output
    constrained to the label/flag schema.
    """

    DEFAULT_MODEL = 'gemini-2.5-flash'
    RESPONSE_SCHEMA = {
        'type': 'OBJECT',
        'properties': {
            'label': {'type': 'STRING', 'enum': sorted(VALID_LABELS)},
            'mentions_individual': {'type': 'BOOLEAN'},
            'toxic': {'type': 'BOOLEAN'},
        },
        'required': ['label', 'mentions_individual', 'toxic'],
    }

    def __init__(self):
        from google import genai  # imported lazily so the dep is optional
        api_key = getattr(settings, 'GEMINI_API_KEY', '')
        if not api_key:
            raise RuntimeError('GEMINI_API_KEY is not configured')
        self.model = getattr(settings, 'GEMINI_MODEL', '') or self.DEFAULT_MODEL
        self._client = genai.Client(api_key=api_key)

    def classify(self, content):
        import json

        from google.genai import types

        response = self._client.models.generate_content(
            model=self.model,
            contents=content,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type='application/json',
                response_schema=self.RESPONSE_SCHEMA,
                temperature=0,
            ),
        )
        text = (response.text or '').strip()
        if not text:
            raise ValueError('model returned an empty response')
        return json.loads(text)


def get_classifier():
    """Return a classifier instance based on the AI_CLASSIFIER_BACKEND setting."""
    backend = getattr(settings, 'AI_CLASSIFIER_BACKEND', 'stub')
    if backend == 'anthropic':
        return AnthropicClassifier()
    if backend == 'gemini':
        return GeminiClassifier()
    return StubClassifier()


def classify_post(content):
    """Classify a post's content.

    Returns ``{'label', 'mentions_individual', 'toxic'}`` or ``None`` when
    classification is disabled, the content is empty, or anything fails.
    """
    if not getattr(settings, 'AI_CLASSIFICATION_ENABLED', False):
        return None
    if not (content or '').strip():
        return None
    try:
        raw = get_classifier().classify(content)
        return _coerce_result(raw)
    except Exception as e:  # never let classification break post creation
        logger.error(f"Post classification failed: {e}")
        return None


def apply_ai_classification(post):
    """Classify ``post`` and persist the label/flags. No-op on failure.

    Returns the result dict if the post was labelled, otherwise ``None``.
    """
    from django.utils import timezone

    result = classify_post(post.content)
    if not result:
        return None
    post.ai_label = result['label']
    post.ai_flag_individual = result['mentions_individual']
    post.ai_flag_toxic = result['toxic']
    post.ai_label_at = timezone.now()
    post.save(update_fields=[
        'ai_label', 'ai_flag_individual', 'ai_flag_toxic', 'ai_label_at',
    ])
    return result
