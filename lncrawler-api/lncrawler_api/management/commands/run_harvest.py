"""Harvest feeder command (standalone / manual use).

The feeder normally runs as a thread inside the scheduler process
(``run_scheduler``). This command is kept for one-shot and manual operation:

Usage:
  python manage.py run_harvest            # loop (standalone feeder)
  python manage.py run_harvest --once     # one loop iteration, then exit
  python manage.py run_harvest --scan     # run one browse scan, then exit
"""

import logging
import signal
import sys
import threading

from django.core.management.base import BaseCommand

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
            sys.exit(harvest_service.run_scan_subprocess())

        stop = threading.Event()

        def _stop(signum, frame):
            logger.info("Received signal %s; stopping harvest feeder", signum)
            stop.set()

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        harvest_service.run_feeder(stop, once=options["once"])
