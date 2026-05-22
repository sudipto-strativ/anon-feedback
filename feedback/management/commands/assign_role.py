"""Assign a Strativ Voice role to a user from the shell.

This exists to keep role management out of the Django admin UI. Browsing
the User admin to flip a role is the kind of low-friction action that
encourages staff to scroll through the user list — exactly the
correlation surface we're trying to close as part of the anonymity
hardening (migration 0012).

Usage:
    python manage.py assign_role <username> <role>

`role` is one of: employee, hr, ceo, admin.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from feedback.models import UserProfile


class Command(BaseCommand):
    help = "Assign a Strativ Voice role to a user (employee | hr | ceo | admin)."

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument(
            'role',
            choices=[choice[0] for choice in UserProfile.ROLE_CHOICES],
        )

    def handle(self, *args, **opts):
        username = opts['username']
        role = opts['role']

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"No user with username '{username}'.")

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = role
        profile.save(update_fields=['role'])

        self.stdout.write(self.style.SUCCESS(
            f"Set role of {username} to {role}."
        ))
