from datetime import date, timedelta
from itertools import groupby

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from lncrawler_api.models import WeeklyNovelView


class Command(BaseCommand):
    help = (
        'Rolls daily view buckets older than the consolidation window into '
        'one bucket per ISO week so the table stays small'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=WeeklyNovelView.CONSOLIDATION_DAYS,
            help='Keep daily buckets for this many days before rolling them up',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be consolidated without changing anything',
        )

    def handle(self, *args, **options):
        cutoff = date.today() - timedelta(days=options['days'])
        dry_run = options['dry_run']

        daily_rows = (
            WeeklyNovelView.objects.filter(
                granularity=WeeklyNovelView.DAY, day__lt=cutoff
            )
            .order_by('novel_id', 'day')
            .values_list('novel_id', 'day', 'views')
        )

        consumed = 0
        weeks_written = 0
        novels_seen = 0

        # Rows arrive ordered by novel (streamed, never fully materialized), so
        # each novel's days can be grouped and rolled up on the fly.
        for novel_id, rows in groupby(
            daily_rows.iterator(chunk_size=2000), key=lambda row: row[0]
        ):
            per_week = {}
            for _, day, views in rows:
                week_start = day - timedelta(days=day.isoweekday() - 1)
                per_week[week_start] = per_week.get(week_start, 0) + views
                consumed += 1

            novels_seen += 1
            if dry_run:
                weeks_written += len(per_week)
                continue

            # One transaction per novel: an interrupted run never leaves the
            # weekly bucket written without its daily rows deleted (or vice versa).
            with transaction.atomic():
                for week_start, views in per_week.items():
                    weekly, created = WeeklyNovelView.objects.get_or_create(
                        novel_id=novel_id,
                        granularity=WeeklyNovelView.WEEK,
                        day=week_start,
                        defaults={'views': views},
                    )
                    if not created:
                        WeeklyNovelView.objects.filter(pk=weekly.pk).update(
                            views=F('views') + views
                        )
                    weeks_written += 1

                WeeklyNovelView.objects.filter(
                    novel_id=novel_id,
                    granularity=WeeklyNovelView.DAY,
                    day__lt=cutoff,
                ).delete()

        action = 'Would roll up' if dry_run else 'Rolled up'
        self.stdout.write(
            self.style.SUCCESS(
                f'{action} {consumed} daily buckets into {weeks_written} weekly '
                f'buckets across {novels_seen} novels (daily rows before {cutoff})'
            )
        )