import time
import threading
import logging
from django.core.management import call_command
from typing import Optional

logger = logging.getLogger('lncrawler_api')

class Scheduler:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.tasks = {}
            self.running = False
            self.thread = None
            self._initialized = True
    
    def register_task(self, interval: int, name: Optional[str] = None):
        """Register a task to run at a specific interval (in seconds)."""
        def decorator(func):
            task_name = name or func.__name__
            self.tasks[task_name] = {
                'function': func,
                'interval': interval,
                'last_run': time.time(),
                'next_run': time.time() + interval
            }
            logger.info(f"Registered scheduled task: {task_name} (interval: {interval}s). {len(self.tasks)} total tasks.")
            return func
        return decorator
    
    def _run_tasks(self):
        """Internal method to run tasks at their scheduled intervals."""
        while self.running:
            current_time = time.time()
            for task_name, task_info in self.tasks.items():
                # Check if it's time to run this task
                if current_time >= task_info['next_run']:
                    logger.info(f"Running scheduled task: {task_name}")
                    try:
                        task_info['function']()
                        task_info['last_run'] = current_time
                        task_info['next_run'] = current_time + task_info['interval']
                        logger.info(f"Task {task_name} completed successfully")
                    except Exception as e:
                        logger.error(f"Error running task {task_name}: {str(e)}", exc_info=True)
            
            # Sleep for a short while to avoid busy waiting
            time.sleep(1)
    
    def start(self):
        """Start the scheduler."""
        if not self.running:
            logger.info("Starting scheduler...")
            self.running = True
            self.thread = threading.Thread(target=self._run_tasks, name="LNCrawler-Scheduler")
            self.thread.daemon = True
            self.thread.start()
            logger.info("Scheduler started")
    
    def stop(self):
        """Stop the scheduler."""
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join(timeout=5)
                self.thread = None
            logger.info("Scheduler stopped")

# Get the singleton scheduler instance
scheduler = Scheduler()

# Task to calculate novel similarities daily
@scheduler.register_task(interval=86400, name="calculate_similarities")  # 86400 seconds = 24 hours
def calculate_novel_similarities():
    """Run the calculate_similarities command to update novel recommendations daily."""
    logger.info("Starting daily novel similarity calculation...")
    try:
        call_command('calculate_similarities')
        logger.info("Daily novel similarity calculation completed successfully")
    except Exception as e:
        logger.error(f"Error in daily novel similarity calculation: {str(e)}", exc_info=True)

# Task to compress low traffic novels daily
# @scheduler.register_task(interval=86400, name="compress_low_traffic")  # 86400 seconds = 24 hours
# def compress_low_traffic_novels():
#     """Run the compress_low_traffic_novels command to compress novels with low weekly views."""
#     logger.info("Starting daily compression of low traffic novels...")
#     try:
#         call_command('compress_low_traffic_novels')
#         logger.info("Daily compression of low traffic novels completed successfully")
#     except Exception as e:
#         logger.error(f"Error in daily compression task: {str(e)}", exc_info=True)

def start_scheduler():
    """Start the scheduler if it's not already running."""
    if not scheduler.running:
        scheduler.start()
