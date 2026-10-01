import signal
import time
import logging

from django.core.management.base import BaseCommand
from django.db import close_old_connections

logger = logging.getLogger('lncrawler_api')


class Command(BaseCommand):
    help = (
        "Run the dedicated crawler worker. Claims queued Job rows from the "
        "database and executes search/download jobs in isolation from the "
        "web workers."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--poll',
            type=float,
            default=2.0,
            help='Seconds to sleep when the queue is empty (default: 2).',
        )
        parser.add_argument(
            '--stale-minutes',
            type=float,
            default=10.0,
            help='Requeue jobs stuck in a running state for this many minutes '
                 '(default: 10).',
        )
        parser.add_argument(
            '--requeue-every',
            type=float,
            default=300.0,
            help='Re-run the stale-job requeue this often, in seconds '
                 '(default: 300; 0 disables periodic requeue).',
        )

    def handle(self, *args, **options):
        from ...services.downloader_service import DownloaderService

        state = {'running': True}

        def _stop(signum, frame):
            logger.info(
                "Crawler worker received signal %s; finishing current job then stopping.",
                signum,
            )
            state['running'] = False

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        DownloaderService.requeue_stale_jobs(minutes=options['stale_minutes'])
        logger.info("Crawler worker started (poll=%ss)", options['poll'])

        requeue_every = options['requeue_every']
        last_requeue = time.monotonic()

        while state['running']:
            close_old_connections()

            # A job that hangs while this worker keeps running would otherwise
            # stay in a running state forever; requeue it periodically.
            if requeue_every > 0 and (time.monotonic() - last_requeue) >= requeue_every:
                last_requeue = time.monotonic()
                try:
                    DownloaderService.requeue_stale_jobs(minutes=options['stale_minutes'])
                except Exception:
                    logger.exception("Failed to requeue stale jobs")

            try:
                claimed = DownloaderService.claim_next_job()
            except Exception:
                logger.exception("Failed to claim a job; retrying")
                time.sleep(options['poll'])
                continue

            if claimed is None:
                time.sleep(options['poll'])
                continue

            job_id, job_type, payload = claimed
            logger.info("Claimed %s job %s", job_type, job_id)
            try:
                DownloaderService.run_job(job_id, job_type, payload)
            except Exception:
                logger.exception("Unhandled error while running job %s", job_id)

        logger.info("Crawler worker stopped.")
