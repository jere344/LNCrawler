from datetime import date, timedelta
from itertools import groupby

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from lncrawler_api.models import WeeklySourceView


class Command(BaseCommand):
    help = (
        'Rolls daily view buckets older than the consolidation window into '
        'one bucket per ISO week so the table stays small'
    )

    def handle(self, *args, **options):
        cutoff = date.today() - timedelta(days=WeeklySourceView.CONSOLIDATION_DAYS)

        daily_rows = (
            WeeklySourceView.objects.filter(
                granularity=WeeklySourceView.DAY, day__lt=cutoff
            )
            .order_by('source_id', 'day')
            .values_list('source_id', 'day', 'views')
        )

        consumed = 0
        weeks_written = 0
        sources_seen = 0

        # Rows arrive ordered by source (streamed, never fully materialized), so
        # each source's days can be grouped and rolled up on the fly.
        for source_id, rows in groupby(
            daily_rows.iterator(chunk_size=2000), key=lambda row: row[0]
        ):
            per_week = {}
            for _, day, views in rows:
                week_start = day - timedelta(days=day.isoweekday() - 1)
                per_week[week_start] = per_week.get(week_start, 0) + views
                consumed += 1

            sources_seen += 1

            # One transaction per source: an interrupted run never leaves the
            # weekly bucket written without its daily rows deleted (or vice versa).
            with transaction.atomic():
                for week_start, views in per_week.items():
                    weekly, created = WeeklySourceView.objects.get_or_create(
                        source_id=source_id,
                        granularity=WeeklySourceView.WEEK,
                        day=week_start,
                        defaults={'views': views},
                    )
                    if not created:
                        WeeklySourceView.objects.filter(pk=weekly.pk).update(
                            views=F('views') + views
                        )
                    weeks_written += 1

                WeeklySourceView.objects.filter(
                    source_id=source_id,
                    granularity=WeeklySourceView.DAY,
                    day__lt=cutoff,
                ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f'Rolled up {consumed} daily buckets into {weeks_written} weekly '
                f'buckets across {sources_seen} sources (daily rows before {cutoff})'
            )
        )
