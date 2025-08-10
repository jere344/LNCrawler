from django.apps import AppConfig
import logging
import os
import sys

logger = logging.getLogger('lncrawler_api')


class LncrawlerApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "lncrawler_api"

    def ready(self):
        """
        Initialize any app-specific tasks when Django starts.
        This is where we start our scheduler.
        """
        # Only start scheduler in production/development servers, not during migrations or other commands
        if (os.environ.get('RUN_MAIN') or 
            'runserver' not in sys.argv and 
            'migrate' not in sys.argv and 
            'makemigrations' not in sys.argv and
            'collectstatic' not in sys.argv):
            
            # Import here to avoid AppRegistryNotReady exception
            from .scheduler import start_scheduler

            try:
                # Start the scheduler
                start_scheduler()
                logger.info("Scheduler initialization completed")
            except Exception as e:
                logger.error(f"Failed to start scheduler: {str(e)}", exc_info=True)
