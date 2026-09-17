from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from research.models import UsageBucket


class Command(BaseCommand):
    help = "Remove expired rate-limit buckets (run daily; active windows are retained)."

    def handle(self, *args, **options):
        count, _ = UsageBucket.objects.filter(
            started_at__lt=timezone.now() - timedelta(days=2)
        ).delete()
        self.stdout.write(f"Removed {count} expired rate-limit buckets.")
