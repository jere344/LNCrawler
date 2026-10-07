import signal
import threading
import time
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger('lncrawler_api')


class Command(BaseCommand):
    help = (
        "Run the database scheduler loop and the harvest feeder in this "
        "process. Exactly one instance should run (the dedicated `scheduler` "
        "service); the scheduler executes the registered periodic tasks with "
        "database-level locking, and the feeder runs in a separate thread so a "
        "long task never stalls it."
    )

    def handle(self, *args, **options):
        # Importing the module registers every @scheduler.register_task.
        from ...scheduler import scheduler
        from ...services import harvest_service

        state = {'running': True}
        stop_harvest = threading.Event()

        def _stop(signum, frame):
            logger.info("Scheduler received signal %s; stopping.", signum)
            state['running'] = False
            stop_harvest.set()

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        scheduler.start()

        feeder = threading.Thread(
            target=harvest_service.run_feeder,
            args=(stop_harvest,),
            name="harvest-feeder",
            daemon=True,
        )
        feeder.start()

        logger.info(
            "Scheduler process running (worker=%s, tasks=%s)",
            scheduler.worker_id,
            ", ".join(sorted(scheduler.registered_tasks)),
        )

        while state['running']:
            time.sleep(1)

        stop_harvest.set()
        # Stop the scheduler first so its DB task locks are released promptly;
        # the feeder may be mid-scan (up to HARVEST_SCAN_TIMEOUT) and must not
        # delay that. It is a daemon thread, so a hung scan is abandoned.
        scheduler.stop()
        feeder.join(timeout=10)
        logger.info("Scheduler process stopped.")
