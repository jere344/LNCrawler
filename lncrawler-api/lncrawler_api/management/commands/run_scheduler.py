import signal
import time
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger('lncrawler_api')


class Command(BaseCommand):
    help = (
        "Run the database scheduler loop in this process. Exactly one "
        "instance should run (the dedicated `scheduler` service); it executes "
        "the registered periodic tasks with database-level locking."
    )

    def handle(self, *args, **options):
        # Importing the module registers every @scheduler.register_task.
        from ...scheduler import scheduler

        state = {'running': True}

        def _stop(signum, frame):
            logger.info("Scheduler received signal %s; stopping.", signum)
            state['running'] = False

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        scheduler.start()
        logger.info(
            "Scheduler process running (worker=%s, tasks=%s)",
            scheduler.worker_id,
            ", ".join(sorted(scheduler.registered_tasks)),
        )

        while state['running']:
            time.sleep(1)

        scheduler.stop()
        logger.info("Scheduler process stopped.")
