"""Long-running harvest feeder.

Singleton (PostgreSQL advisory lock). Each loop reconciles candidate results,
runs a browse scan when the pending catalogue is low, and enqueues download
Jobs for idle sources. Controlled from the admin via HarvestConfig; the process
is meant to stay up.

Usage:
  python manage.py run_harvest            # loop
  python manage.py run_harvest --once     # one loop iteration, then exit
  python manage.py run_harvest --scan     # run one browse scan, then exit
"""

import logging
import os
import signal
import sys
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from ...services import harvest_service

logger = logging.getLogger("lncrawler_api")


class Command(BaseCommand):
    help = "Background harvest feeder: discover novels and queue downloads."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run one loop iteration and exit.")
        parser.add_argument("--scan", action="store_true", help="Run one browse scan and exit.")

    def handle(self, *args, **options):
        if options["scan"]:
            code = harvest_service.run_scan_subprocess()
            sys.exit(code)

        stop = {"flag": False}

        def _stop(signum, frame):
            logger.info("Received signal %s; stopping harvest feeder", signum)
            stop["flag"] = True

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        interval = int(os.environ.get("HARVEST_INTERVAL", "20"))
        logger.info("Harvest feeder started (interval=%ss)", interval)

        try:
            while not stop["flag"]:
                if not harvest_service.acquire_feeder_lock():
                    # Another feeder owns the lock. Wait instead of exiting, so a
                    # stray replica does not restart-loop under `restart: unless-stopped`.
                    logger.info("Harvest lock held elsewhere; retrying in %ss", interval)
                    if options["once"]:
                        return
                    time.sleep(interval)
                    continue
                try:
                    self._tick()
                finally:
                    harvest_service.release_feeder_lock()
                if options["once"]:
                    break
                time.sleep(interval)
        finally:
            logger.info("Harvest feeder stopped")

    def _tick(self):
        config = harvest_service.get_config()
        if not config.enabled:
            return

        touched = harvest_service.reconcile()
        if touched:
            logger.info("Harvest: reconciled %s candidate(s)", touched)

        if harvest_service.should_scan(config):
            harvest_service.run_scan_subprocess()
            # Record the attempt even when the scan failed, so a broken scan is
            # retried after the normal cooldown instead of every tick.
            config.refresh_from_db()
            config.last_harvest_at = timezone.now()
            config.save(update_fields=["last_harvest_at", "updated_at"])

        enqueued = harvest_service.enqueue_ready(config)
        if enqueued:
            logger.info("Harvest: queued %s download(s)", enqueued)
