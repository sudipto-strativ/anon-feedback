from django.core.management.base import BaseCommand
from django.utils import timezone

from feedback.models import SlackQueueItem
from feedback.notifications import send_slack_message


class Command(BaseCommand):
    help = "Send a Slack digest of all queued post/comment notifications and clear the queue."

    def handle(self, *args, **options):
        items = list(SlackQueueItem.objects.all())
        if not items:
            self.stdout.write("No queued Slack notifications. Nothing sent.")
            return

        posts = [i for i in items if i.event_type == SlackQueueItem.EVENT_POST]
        comments = [i for i in items if i.event_type == SlackQueueItem.EVENT_COMMENT]

        date_str = timezone.localdate().strftime("%A, %d %B %Y")
        lines = [f":calendar: *Strativ Voice — Daily Digest ({date_str})*\n"]

        if posts:
            lines.append(f":mega: *{len(posts)} new feedback post{'s' if len(posts) != 1 else ''}*")
            for item in posts:
                lines.append(item.message)
            lines.append("")

        if comments:
            lines.append(f":speech_balloon: *{len(comments)} new comment{'s' if len(comments) != 1 else ''}*")
            for item in comments:
                lines.append(item.message)

        send_slack_message("\n".join(lines))
        SlackQueueItem.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Digest sent: {len(posts)} post(s), {len(comments)} comment(s). Queue cleared."
            )
        )
