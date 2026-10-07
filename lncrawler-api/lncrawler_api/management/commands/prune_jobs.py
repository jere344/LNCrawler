"""Delete finished Job rows older than the retention window.

A continuously running harvest feeder grows the Job table forever; this trims
terminal jobs (download_completed / failed) once they are old enough. Jobs still
referenced by a *queued* HarvestCandidate are kept so reconciliation can read
their result.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Delete finished Job rows older than the retention window."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        from ...models import HarvestCandidate, Job

        cutoff = timezone.now() - timedelta(days=options["days"])
        stale = Job.objects.filter(
            status__in=[Job.STATUS_DOWNLOAD_COMPLETED, Job.STATUS_FAILED],
            updated_at__lt=cutoff,
        )
        protected = HarvestCandidate.objects.filter(
            status=HarvestCandidate.STATUS_QUEUED
        ).exclude(job_id__isnull=True).values_list("job_id", flat=True)
        stale = stale.exclude(id__in=list(protected))

        if options["dry_run"]:
            self.stdout.write(f"Would delete {stale.count()} old job(s)")
            return
        deleted, _ = stale.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} old job(s)"))
