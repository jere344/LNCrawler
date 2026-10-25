import os
import sys

from django.core.management.base import BaseCommand


def _apply_memory_limit():
    """Optionally cap this job process's address space.

    Off by default: RLIMIT_AS also applies to Playwright's Chromium child, which
    reserves large virtual mappings, so a too-low limit breaks browser fallbacks.
    Set CRAWLER_JOB_MEM_LIMIT_MB (e.g. 768) to enable a hard cap per job.
    """
    limit_mb = int(os.environ.get("CRAWLER_JOB_MEM_LIMIT_MB", "0") or "0")
    if limit_mb <= 0:
        return
    try:
        import resource

        limit = limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ImportError, ValueError, OSError):
        pass


class Command(BaseCommand):
    help = (
        "Run a single crawler job by id, then exit. Invoked by the crawler "
        "supervisor as a short-lived subprocess so each job's memory is released "
        "on exit. Reuses DownloaderService.run_job unchanged."
    )
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("job_id")
        parser.add_argument("job_type")
        parser.add_argument("payload", nargs="?", default="")

    def handle(self, *args, **options):
        from ...services.downloader_service import DownloaderService

        from ...models import Job

        _apply_memory_limit()
        DownloaderService.run_job(
            options["job_id"], options["job_type"], options["payload"]
        )

        if options["job_type"] not in (Job.JOB_TYPE_DOWNLOAD, Job.JOB_TYPE_EPUB):
            # Sources cut off at the search deadline keep running in executor
            # threads, which a normal exit joins; skip that so the slot and
            # memory are freed as soon as the results are saved.
            import logging

            from django.db import connections

            connections.close_all()
            logging.shutdown()
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)
