# Strativ Voice

An anonymous feedback platform for Strativ AB. Employees can post feedback anonymously, interact with others' posts, and management can track and update the status of each feedback item.

## Features

- Anonymous feedback posting with like/dislike voting (devrant-style)
- Comment threads with user group badges (Employee / HR / CEO)
- Feed views: Recent, Top, Hot
- List view with search and status filtering
- Task status management for CEO/HR (Pending, In Progress, Done, Rejected)
- ETA (estimated completion date) per feedback item
- Slack bot notifications for new posts, comments, and status updates
- Email notifications to a configurable list of recipients on new posts
- Sidebar quick stats (Total Posts, In Progress, Resolved)

## User Groups

| Group | How Assigned | Capabilities |
|---|---|---|
| Employee | Self-registration | Post feedback, like/dislike, comment |
| HR | By Django superadmin | All employee actions + update post status and ETA |
| CEO | By Django superadmin | All employee actions + update post status and ETA |
| Superadmin | Django default | Full admin access, assigns HR/CEO roles |

## Requirements

- Python 3.9+
- pip packages listed in `requirements.txt`

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set the required values:

```env
SECRET_KEY=your-secret-key-here       # generate with: python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
DEBUG=True                             # set to False in production
DEFAULT_FROM_EMAIL=noreply@example.com
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
SLACK_WEBHOOK_URL=                     # optional, see Slack Setup below
```

### 3. Apply migrations

```bash
python3 manage.py migrate
```

### 4. Create a superadmin

```bash
python3 manage.py createsuperuser
```

### 5. Run the development server

```bash
python3 manage.py runserver
```

Visit `http://127.0.0.1:8000/`

## Admin Panel

Access at `http://127.0.0.1:8000/admin/` using your superadmin credentials.

### Assign CEO or HR role to a user

1. Go to **Users** in the admin panel
2. Click the user
3. Scroll to the **Profile** section at the bottom
4. Change **Role** to `HR` or `CEO`
5. Save

### Configure email notifications

Go to **Notification Emails** in the admin panel and add email addresses that should be notified whenever a new feedback post is created.

### Configure Slack

Go to **Slack Configurations** in the admin panel and add a row with:
- **Webhook URL**: your Slack incoming webhook URL
- **Channel name**: optional label (e.g. `#feedback`)
- **Is active**: checked

Alternatively, set `SLACK_WEBHOOK_URL` in `.env` — the notification code will use the DB config first and fall back to the env variable.

Slack notifications are sent for:
- New feedback post created
- New comment added
- Post status or ETA updated

## Project Structure

```
strativ_voice/
├── manage.py
├── requirements.txt
├── .env.example
├── strativ_voice/          # Django project settings
│   ├── settings.py
│   └── urls.py
└── feedback/               # Main application
    ├── models.py           # UserProfile, Post, Comment, Vote, NotificationEmail, SlackConfig
    ├── views.py            # All views
    ├── forms.py            # RegisterForm, PostForm, CommentForm, StatusUpdateForm
    ├── notifications.py    # Slack and email notification helpers
    ├── signals.py          # Auto-creates UserProfile on user creation
    ├── context_processors.py
    ├── templatetags/
    │   └── feedback_extras.py   # timesince_short, truncate_chars, get_item, score_class
    └── templates/feedback/
        ├── base.html
        ├── feed.html
        ├── list_view.html
        ├── post_detail.html
        ├── post_create.html
        ├── login.html
        ├── register.html
        └── partials/
            ├── post_card.html
            └── comment.html
```

## Production Notes

- Set `DEBUG=False` in `.env`
- Set a strong, unique `SECRET_KEY`
- Configure a real email backend (e.g. SMTP) instead of the console backend
- Serve static files via a web server (nginx) or a storage backend (S3)
- Use a production database (PostgreSQL recommended)
