from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone

from lncrawler_api.models import Job, NovelFromSource

# Marker used to recognise our own in-flight jobs. Only one is ever queued at a
# time, so the batch runs on a single crawler worker even with several replicas.
UPDATE_QUERY = "Weekly popular source update"

# A source updated within this many days is considered fresh and skipped.
# (7 - 1: the weekly run should not re-fetch what was refreshed < 7 days ago.)
FRESH_DAYS = 6

_PENDING_STATUSES = [
    Job.STATUS_CREATED,
    Job.STATUS_SEARCHING,
    Job.STATUS_DOWNLOADING,
]


class Command(BaseCommand):
    help = (
        "Queue the next update for the most popular sources (by total views). "
        "At most one update is in flight, so the whole batch runs on a single "
        "crawler thread. Sources already updated in the last 6 days are skipped."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--top',
            type=int,
            default=20,
            help='Only consider this many most popular sources (default: 20)',
        )
        parser.add_argument(
            '--fresh-days',
            type=int,
            default=FRESH_DAYS,
            help='Skip sources updated within this many days (default: 6)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show which source would be queued without creating a job',
        )

    def handle(self, *args, **options):
        top = options['top']
        fresh_days = options['fresh_days']
        dry_run = options['dry_run']

        # One popular-update job at a time keeps the batch on a single thread
        # no matter how many crawler workers are running.
        in_flight = Job.objects.filter(
            query=UPDATE_QUERY, status__in=_PENDING_STATUSES
        ).exists()
        if in_flight:
            self.stdout.write("A popular source update is already in flight; skipping.")
            return

        cutoff = timezone.now() - timedelta(days=fresh_days)

        # Restrict the candidate pool to the most popular sources, then pick the
        # most popular one that is stale. A NULL last_chapter_update means it was
        # never updated, so it qualifies.
        top_ids = list(
            NovelFromSource.objects.exclude(source_url__isnull=True)
            .exclude(source_url='')
            .order_by('-total_views')
            .values_list('pk', flat=True)[:top]
        )

        # A source whose most recent job failed is left alone: retrying it every
        # tick would just loop failures. It becomes eligible again once a newer
        # attempt (manual or automatic) succeeds.
        last_job_status = Subquery(
            Job.objects.filter(target_url=OuterRef('source_url'))
            .order_by('-updated_at')
            .values('status')[:1]
        )

        source = (
            NovelFromSource.objects.filter(pk__in=top_ids)
            .filter(Q(last_chapter_update__isnull=True) | Q(last_chapter_update__lt=cutoff))
            .annotate(last_job_status=last_job_status)
            .filter(Q(last_job_status__isnull=True) | ~Q(last_job_status=Job.STATUS_FAILED))
            .order_by('-total_views')
            .first()
        )

        if source is None:
            self.stdout.write(
                self.style.SUCCESS("No stale popular source to update.")
            )
            return

        label = f"{source.title} ({source.external_source.source_name})"
        if dry_run:
            self.stdout.write(self.style.WARNING(f"Would queue update: {label}"))
            return

        Job.objects.create(
            status=Job.STATUS_CREATED,
            job_type=Job.JOB_TYPE_DOWNLOAD,
            query=UPDATE_QUERY,
            target_url=source.source_url,
        )
        self.stdout.write(self.style.SUCCESS(f"Queued update: {label}"))
