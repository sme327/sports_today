from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from services.daily_feed import precompute_days


class Command(BaseCommand):
    help = "Refresh schedules and precompute today's and tomorrow's public feeds."

    def handle(self, *args, **options):
        today = timezone.localdate()
        for result in precompute_days([today, today + timedelta(days=1)]):
            self.stdout.write(
                self.style.SUCCESS(
                    f"{result['date']}: {result['games']} games, "
                    f"{result['opportunities']} opportunities, "
                    f"{result.get('matchup_pages', 0)} matchup pages, "
                    f"{result['total_seconds']:.1f}s"
                )
            )
