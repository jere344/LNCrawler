import time
import threading
import logging
import os
import uuid
from django.core.management import call_command
from django.utils import timezone
from typing import Optional, Callable, Dict
from .models import ScheduledTask

logger = logging.getLogger('lncrawler_api')

class DatabaseScheduler:
    """
    A database-backed scheduler that prevents multiple workers from executing 
    the same task simultaneously using database-level locking.
    """
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
            self.registered_tasks: Dict[str, Callable] = {}
            self.running = False
            self.thread = None
            self.worker_id = f"worker-{os.getpid()}-{uuid.uuid4().hex[:8]}"
            self._initialized = True
    
    def register_task(self, interval: int, name: Optional[str] = None):
        """Register a task to run at a specific interval (in seconds)."""
        def decorator(func):
            task_name = name or func.__name__
            self.registered_tasks[task_name] = func
            
            # Ensure the task exists in the database
            try:
                ScheduledTask.get_or_create_task(task_name, interval)
                logger.info(f"Registered scheduled task: {task_name} (interval: {interval}s)")
            except Exception as e:
                logger.error(f"Failed to register task {task_name}: {str(e)}")
            
            return func
        return decorator
    
    def _run_task_loop(self):
        """Main loop that checks for and executes scheduled tasks."""
        logger.info(f"Scheduler worker {self.worker_id} started")
        
        while self.running:
            try:
                # Clean up stale locks periodically
                ScheduledTask.cleanup_stale_locks()
                
                # Check each registered task
                for task_name in self.registered_tasks.keys():
                    if not self.running:
                        break
                    
                    # Try to acquire lock on this task
                    task = ScheduledTask.acquire_lock(task_name, self.worker_id)
                    
                    if task:
                        # We got the lock, execute the task
                        self._execute_task(task)
                
            except Exception as e:
                logger.error(f"Error in scheduler main loop: {str(e)}", exc_info=True)
            
            # Sleep for a short while before checking again
            time.sleep(5)  # Check every 5 seconds
        
        logger.info(f"Scheduler worker {self.worker_id} stopped")
    
    def _execute_task(self, task: ScheduledTask):
        """Execute a specific task and handle the result."""
        task_function = self.registered_tasks.get(task.name)
        
        if not task_function:
            logger.error(f"Task function not found for '{task.name}'")
            task.release_lock(success=False, error_message="Task function not found")
            return
        
        logger.info(f"Executing task '{task.name}' (worker: {self.worker_id})")
        
        try:
            # Execute the task
            task_function()
            
            # Mark as successful
            task.release_lock(success=True)
            logger.info(f"Task '{task.name}' completed successfully")
            
        except Exception as e:
            error_msg = f"Task execution failed: {str(e)}"
            logger.error(f"Error executing task '{task.name}': {error_msg}", exc_info=True)
            task.release_lock(success=False, error_message=error_msg)
    
    def start(self):
        """Start the scheduler."""
        if not self.running:
            logger.info(f"Starting database scheduler (worker: {self.worker_id})...")
            self.running = True
            self.thread = threading.Thread(target=self._run_task_loop, name=f"DatabaseScheduler-{self.worker_id}")
            self.thread.daemon = True
            self.thread.start()
            logger.info("Database scheduler started")
        else:
            logger.info("Database scheduler is already running")
    
    def stop(self):
        """Stop the scheduler."""
        if self.running:
            logger.info("Stopping database scheduler...")
            self.running = False
            if self.thread:
                self.thread.join(timeout=10)
                self.thread = None
            logger.info("Database scheduler stopped")

# Get the singleton scheduler instance
scheduler = DatabaseScheduler()

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
        raise  # Re-raise to mark task as failed

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
#         raise  # Re-raise to mark task as failed

def start_scheduler():
    """Start the scheduler if it's not already running."""
    if not scheduler.running:
        scheduler.start()
