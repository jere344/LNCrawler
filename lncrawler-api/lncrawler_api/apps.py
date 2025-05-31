from django.apps import AppConfig
import logging
import os

logger = logging.getLogger('lncrawler_api')


class LncrawlerApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "lncrawler_api"

    def ready(self):
        """
        Initialize any app-specific tasks when Django starts.
        This is where we start our scheduler.
        """
        # Only start scheduler in the master process
        # Check if this is a Gunicorn worker process
        if os.environ.get('RUN_MAIN') or os.environ.get('WORKER_ID'):
            return
            
        # Import here to avoid AppRegistryNotReady exception
        from .scheduler import start_scheduler

        # Start the scheduler
        start_scheduler()
