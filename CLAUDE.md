# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Django 4.2 anonymous feedback platform. Members post feedback; HR/CEO manage status. Notifications via email + Slack.

## Commands

```bash
# Setup
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# Tests
python manage.py test                                                              # all
python manage.py test feedback                                                     # app only
python manage.py test feedback.tests.test_models                                   # single file
python manage.py test feedback.tests.test_views.FeedViewTest.test_get_recent_tab   # single test

# Production
python manage.py collectstatic --noinput
gunicorn strativ_voice.wsgi:application
```

No lint/format tooling configured.

## Environment Variables

Loaded from `.env` (see `.env.example`):

| Var | Default | Notes |
|-----|---------|-------|
| `SECRET_KEY` | dev key | required in prod |
| `DEBUG` | `True` | |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | CSV |
| `DATABASE_URL` | SQLite | optional |
| `EMAIL_BACKEND` | console | set to SMTP for real email |
| `SENDGRID_API_KEY` | — | for SendGrid SMTP |
| `DEFAULT_FROM_EMAIL` | — | |
| `SLACK_WEBHOOK_URL` | — | DB config takes precedence |
| `SITE_URL` | `http://localhost:8000` | used in notification links |

## Architecture

### Models (`feedback/models.py`)

- **UserProfile** — 1:1 with Django User; roles: `member` (was "employee"), `hr`, `ceo`
- **Post** — core feedback; status: `pending/in_progress/done/rejected`; has ETA + remark
- **Comment** — on posts; content optional (image-only allowed); supports Markdown
- **Vote** — like/dislike on posts or comments; unique per user+target; same vote = delete, different = switch
- **Favourite** — user bookmarks on posts
- **PostAttachment** — images/PDF/Word/Excel on posts (max 10 MB each)
- **CommentImage** — image on comments (max 5 MB)
- **NotificationEmail** — admin-configured recipient list
- **SlackConfig** — DB-stored webhook URL (overrides env var)

### Views & Routing

Main app: `feedback/views.py` + `feedback/urls.py`. Project routing: `strativ_voice/urls.py`.

Key views:
- Feed (`/`, `/feed/`) — tabs: recent / top (by score) / hot (recent comments)
- List (`/list/`) — search + status filter, paginated
- Post detail (`/post/<id>/`) — full post, comments, status form (CEO/HR only)
- Vote/favourite — JSON toggle endpoints (`/post/<id>/vote/`, `/post/<id>/favourite/`)
- Status update (`/post/<id>/update-status/`) — CEO/HR only; remark required for done/rejected

### Authorization

- Most views: `@login_required`
- Status/ETA updates: `user.profile.role in ('hr', 'ceo')` check in view
- Role assignment: superadmin via Django admin panel
- Session timeout: 24 hours

### Notification Pipeline

`feedback/notifications.py` — called from views on post/comment/status changes.
- Email: Django `send_mail()` → recipients from `NotificationEmail` model
- Slack: `requests.post()` to webhook URL (DB → env fallback)

### Key Patterns

- **N+1 prevention**: views use `select_related('author__profile')` + `prefetch_related('votes', 'comments')`, then build vote-map dict once and pass to template
- **Markdown safety**: `markdown()` → `bleach.clean()` pipeline in `feedback_extras.py:render_markdown`
- **Signal**: `feedback/signals.py` auto-creates `UserProfile` on User creation; registered in `feedback/apps.py`
- **Context processor**: `feedback/context_processors.py` injects sidebar stats into all templates
- **Computed properties**: `post.score`, `post.like_count`, `post.dislike_count` as model properties
- **Admin UI**: Jazzmin (`django-jazzmin`) for enhanced admin panel
- **Static files**: WhiteNoise — no separate web server needed

### Tests

7 test files under `feedback/tests/`. Use `unittest.mock` for email and Slack calls. No fixtures — tests create objects directly.
