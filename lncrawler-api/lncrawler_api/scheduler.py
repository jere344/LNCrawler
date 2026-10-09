import time
import threading
import logging
import os
import uuid
from django.conf import settings
from django.core.management import call_command
from typing import Optional, Callable, Dict
from .models import ScheduledTask

logger = logging.getLogger('lncrawler_api')


def scheduler_enabled():
    """Master switch for automatic maintenance tasks.

    Set SCHEDULER_ENABLED=False to keep the scheduler process running (so it
    still cleans up stale locks) while suppressing every registered task, e.g.
    so they can be triggered manually from the admin instead.
    """
    value = os.environ.get("SCHEDULER_ENABLED", "True").strip().lower()
    return value not in ("0", "false", "no", "off", "")


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
    
    def _remove_orphan_tasks(self):
        """Delete scheduler rows whose task is no longer registered.

        Removing a command leaves its ScheduledTask row behind; the loop only
        ever executes registered names, so those rows are dead weight.
        """
        deleted, _ = ScheduledTask.objects.exclude(
            name__in=self.registered_tasks.keys()
        ).delete()
        if deleted:
            logger.info("Removed %s orphaned scheduled task row(s)", deleted)

    def _run_task_loop(self):
        """Main loop that checks for and executes scheduled tasks."""
        logger.info(f"Scheduler worker {self.worker_id} started")
        self._remove_orphan_tasks()
        
        while self.running:
            try:
                # Clean up stale locks periodically
                ScheduledTask.cleanup_stale_locks()
                
                # Master switch: when disabled, keep the worker alive (stale-lock
                # cleanup above still runs) but never pick up a task.
                if not scheduler_enabled():
                    time.sleep(5)
                    continue
                
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
        
        # Keep extending the lock while the task runs so another worker cannot
        # reclaim it and run the same task twice concurrently.
        heartbeat_stop = threading.Event()
        
        def _heartbeat_loop():
            while not heartbeat_stop.wait(300):
                if not task.heartbeat():
                    logger.warning(f"Task '{task.name}': lost lock while running, stopping heartbeat")
                    break
        
        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop, name=f"heartbeat-{task.name}", daemon=True
        )
        heartbeat_thread.start()
        
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
        finally:
            heartbeat_stop.set()
    
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

# Rebuild novel recommendations weekly (heavy O(N^2)-ish sweep; weekly is plenty).
@scheduler.register_task(interval=604800, name="calculate_similarities")  # 604800 seconds = 7 days
def calculate_novel_similarities():
    """Run the calculate_similarities command to update novel recommendations weekly."""
    logger.info("Starting weekly novel similarity calculation...")
    try:
        call_command('calculate_similarities')
        logger.info("Weekly novel similarity calculation completed successfully")
    except Exception as e:
        logger.error(f"Error in weekly novel similarity calculation: {str(e)}", exc_info=True)
        raise  # Re-raise to mark task as failed

# Rebuild the cross-source duplicate queue weekly, after similarities so the
# text signal is fresh. Auto-merge stays off until MERGE_AUTO_SCORE is tuned.
@scheduler.register_task(interval=604800, name="find_merge_candidates")  # 7 days
def find_merge_candidates_task():
    logger.info("Scanning for duplicate novel candidates...")
    try:
        call_command('find_merge_candidates')
        logger.info("Duplicate novel scan completed successfully")
    except Exception as e:
        logger.error(f"Error scanning for duplicate novels: {str(e)}", exc_info=True)
        raise  # Re-raise to mark task as failed

# Adjudicate the gray band with the LLM, a few calls per tick, only when an API
# key is configured. Bounded per tick (settings.MERGE_LLM_LIMIT_PER_TICK) and by
# a daily budget tracked on MergeCandidate.llm_checked_at, so a slow or
# rate-limited provider cannot block the rest of the maintenance loop.
@scheduler.register_task(
    interval=int(getattr(settings, "MERGE_LLM_INTERVAL", 300)), name="judge_merge_candidates"
)
def judge_merge_candidates_task():
    from django.conf import settings as _settings

    if not getattr(_settings, "MERGE_LLM_API_KEY", ""):
        return  # zero-LLM fallback: the review queue still works.
    logger.info("Judging merge candidates with LLM...")
    try:
        call_command('judge_merge_candidates')
        logger.info("Merge candidate LLM judging completed")
    except Exception as e:
        logger.error(f"Error judging merge candidates: {str(e)}", exc_info=True)
        raise

# Task to compress low traffic novels weekly.
# Guardrails live in the command itself: single-threaded 7z (-mmt=1), low CPU
# priority (nice), a pause between sources, and an id-batched scan. It targets
# cold novels only and is allowed to run for a long time.
@scheduler.register_task(interval=604800, name="compress_low_traffic")  # 604800 seconds = 7 days
def compress_low_traffic_novels():
    """Run the compress_low_traffic_novels command to compress novels with low weekly views."""
    logger.info("Starting compression of low traffic novels...")
    try:
        # Bound each run so a cold catalogue can never turn the first execution
        # into a multi-day job; leftovers are picked up on the next weekly run.
        call_command('compress_low_traffic_novels', max_sources=500)
        logger.info("Compression of low traffic novels completed successfully")
    except Exception as e:
        logger.error(f"Error in compression task: {str(e)}", exc_info=True)
        raise  # Re-raise to mark task as failed

# Roll daily view buckets older than the retention window into weekly buckets.
# Daily granularity only matters for the rolling 7-day display; older history
# is kept as one row per ISO week so the table doesn't grow forever.
@scheduler.register_task(interval=604800, name="consolidate_source_views")  # 604800 seconds = 7 days
def consolidate_source_views():
    """Run the consolidate_source_views command to roll old daily views into weekly buckets."""
    logger.info("Starting consolidation of old daily view buckets...")
    try:
        call_command('consolidate_source_views')
        logger.info("Daily view bucket consolidation completed successfully")
    except Exception as e:
        logger.error(f"Error consolidating daily view buckets: {str(e)}", exc_info=True)
        raise  # Re-raise to mark task as failed

# Top up the popular-source refresh queue. Runs often but queues at most one job
# per tick and skips sources refreshed in the last 6 days, so each source ends up
# updated about weekly while the batch always stays on a single crawler thread
# (even with several crawler replicas).
@scheduler.register_task(interval=3600, name="update_popular_sources")  # hourly
def update_popular_sources():
    """Queue the next update for the most popular sources."""
    logger.info("Queueing next popular source update...")
    try:
        call_command('update_popular_sources', top=20)
        logger.info("Popular source update queue check completed")
    except Exception as e:
        logger.error(f"Error queueing popular source update: {str(e)}", exc_info=True)
        raise  # Re-raise to mark task as failed

# Progressively prune orphan novels, empty sources and dead-source duplicates.
# Bounded --limit per run so a 40k-novel first pass spreads over many runs.
@scheduler.register_task(interval=600, name="prune_library")
def prune_library_task():
    import os
    if os.getenv("LNCRAWL_PRUNE_APPLY", "1").lower() in ("0", "false", "no"):
        return
    logger.info("Pruning library (bounded batch)...")
    try:
        call_command('prune_library', apply=True, limit=200)
        logger.info("Library prune batch completed")
    except Exception as e:
        logger.error(f"Error pruning library: {str(e)}", exc_info=True)
        raise

# Trim terminal Job rows so a continuously running harvest feeder cannot grow
# the job table without bound. Keeps jobs still referenced by queued candidates.
@scheduler.register_task(interval=86400, name="prune_jobs")  # daily
def prune_jobs_task():
    logger.info("Pruning old finished jobs...")
    try:
        call_command('prune_jobs')
        logger.info("Old job prune completed")
    except Exception as e:
        logger.error(f"Error pruning old jobs: {str(e)}", exc_info=True)
        raise

def start_scheduler():
    """Start the scheduler if it's not already running."""
    if not scheduler.running:
        scheduler.start()
