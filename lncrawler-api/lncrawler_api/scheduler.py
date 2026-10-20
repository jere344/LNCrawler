import time
import threading
import logging
import os
import subprocess
import sys
import uuid
from django.conf import settings
from django.core.management import call_command
from django.db import close_old_connections
from typing import Optional, Callable, Dict
from .models import ScheduledTask
from .services import llm_service

logger = logging.getLogger('lncrawler_api')

HOUR = 3600
DAY = 86400
WEEK = 604800


def call_command_isolated(*args):
    """Run a management command in a child process.

    Heavy batch jobs (dense similarity matrices, embedding scans) peak at
    hundreds of MB; run in-process, that memory stays with this long-lived
    scheduler after the job ends. A child process gives it back to the OS.
    """
    subprocess.run([sys.executable, "manage.py", *args], cwd=settings.BASE_DIR, check=True)


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
                # This is a plain background thread, so Django's per-request
                # connection cleanup never runs here. Revalidate the connection
                # each iteration: CONN_MAX_AGE closes it by age and a DB
                # restart/failover leaves a dead wrapper that would otherwise
                # raise "the connection is closed" forever.
                close_old_connections()

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
                close_old_connections()
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


def _run_job(start, done, failed, run):
    """Log ``start``, call ``run``, then log ``done``.

    An exception is logged as ``failed`` (formatted with ``error``) with its
    traceback, then re-raised so the task is marked as failed.
    """
    logger.info(start)
    try:
        run()
        logger.info(done)
    except Exception as e:
        logger.error(failed.format(error=str(e)), exc_info=True)
        raise

# Rebuild novel recommendations weekly (heavy O(N^2)-ish sweep; weekly is plenty).
@scheduler.register_task(interval=WEEK, name="calculate_similarities")  # 7 days
def calculate_novel_similarities():
    """Run the calculate_similarities command to update novel recommendations weekly."""
    _run_job(
        "Starting weekly novel similarity calculation...",
        "Weekly novel similarity calculation completed successfully",
        "Error in weekly novel similarity calculation: {error}",
        lambda: call_command_isolated('calculate_similarities'),
    )

# Rebuild the cross-source duplicate queue weekly, after similarities so the
# text signal is fresh. Auto-merge stays off until MERGE_AUTO_SCORE is tuned.
@scheduler.register_task(interval=WEEK, name="find_merge_candidates")  # 7 days
def find_merge_candidates_task():
    _run_job(
        "Scanning for duplicate novel candidates...",
        "Duplicate novel scan completed successfully",
        "Error scanning for duplicate novels: {error}",
        lambda: call_command_isolated('find_merge_candidates'),
    )

# Adjudicate the gray band through the LLMRequest queue (services/llm_tasks.py,
# NovelMergeTask), like the R18 one. Only when an API key is configured. Bounded
# per tick (settings.MERGE_LLM_LIMIT_PER_TICK) and by the shared daily budget, so a
# slow or rate-limited provider cannot block the rest of the maintenance loop.
@scheduler.register_task(
    interval=int(settings.MERGE_LLM_INTERVAL), name="judge_merge_candidates"
)
def judge_merge_candidates_task():
    if not llm_service.is_configured():
        return  # zero-LLM fallback: the review queue still works.
    _run_job(
        "Judging merge candidates with LLM...",
        "Merge candidate LLM judging completed",
        "Error judging merge candidates: {error}",
        lambda: call_command('run_llm_requests', 'novel_merge'),
    )

# Rebuild tag merge clusters daily: embeds new tags and groups likely duplicates.
# Unchanged groups are skipped by signature, so a re-run only adds new work.
@scheduler.register_task(interval=DAY, name="find_tag_merge_candidates")  # daily
def find_tag_merge_candidates_task():
    _run_job(
        "Scanning for duplicate tag candidates...",
        "Duplicate tag scan completed successfully",
        "Error scanning for duplicate tags: {error}",
        lambda: call_command_isolated('find_tag_merge_candidates'),
    )

# Ask the LLM to judge pending tag clusters, a few calls per tick, only when the
# merge LLM key is configured. Bounded per tick and by a daily call budget.
@scheduler.register_task(
    interval=int(settings.TAG_LLM_INTERVAL), name="judge_tag_clusters"
)
def judge_tag_clusters_task():
    if not llm_service.is_configured():
        return  # zero-LLM fallback: clusters stay pending until a key is set.
    _run_job(
        "Judging tag clusters with LLM...",
        "Tag cluster LLM judging completed",
        "Error judging tag clusters: {error}",
        lambda: call_command('judge_tag_clusters'),
    )

# Flag R18 tags through the generic LLMRequest queue (services/llm_tasks.py, TagR18Task).
# Bounded per tick and by a daily token budget; needs the merge LLM key.
@scheduler.register_task(
    interval=int(settings.TAG_R18_LLM_INTERVAL), name="run_llm_tag_r18"
)
def run_llm_tag_r18_task():
    if not llm_service.is_configured():
        return  # zero-LLM fallback: nothing is queued or sent.
    _run_job(
        "Classifying R18 tags with LLM...",
        "R18 tag LLM classification completed",
        "Error classifying R18 tags: {error}",
        lambda: call_command('run_llm_requests', 'tag_r18'),
    )

# Find duplicate author names daily: merges normalized and mixed-script matches,
# queues cross-source pairs for the LLM judge. Re-runs skip known pairs by signature.
@scheduler.register_task(interval=DAY, name="find_author_candidates")  # daily
def find_author_candidates_task():
    _run_job(
        "Scanning for duplicate author candidates...",
        "Duplicate author scan completed successfully",
        "Error scanning for duplicate authors: {error}",
        lambda: call_command_isolated('find_author_candidates'),
    )

# Ask the LLM to judge queued author pairs (services/llm_tasks.py, AuthorMergeTask).
# Same cadence and per-tick cap as judge_merge_candidates; the shared daily budget
# bounds the total. Only when the merge LLM key is configured.
@scheduler.register_task(
    interval=int(settings.MERGE_LLM_INTERVAL), name="judge_author_candidates"
)
def judge_author_candidates_task():
    if not llm_service.is_configured():
        return  # zero-LLM fallback: pairs stay pending until a key is set.
    _run_job(
        "Judging author candidates with LLM...",
        "Author candidate LLM judging completed",
        "Error judging author candidates: {error}",
        lambda: call_command('run_llm_requests', 'author_merge'),
    )

# Task to compress low traffic novels weekly.
# Guardrails live in the command itself: single-threaded 7z (-mmt=1), low CPU
# priority (nice), a pause between sources, and an id-batched scan. It targets
# cold novels only and is allowed to run for a long time.
@scheduler.register_task(interval=WEEK, name="compress_low_traffic")  # 7 days
def compress_low_traffic_novels():
    """Run the compress_low_traffic_novels command to compress novels with low weekly views."""
    # Bound each run so a cold catalogue can never turn the first execution
    # into a multi-day job; leftovers are picked up on the next weekly run.
    _run_job(
        "Starting compression of low traffic novels...",
        "Compression of low traffic novels completed successfully",
        "Error in compression task: {error}",
        lambda: call_command('compress_low_traffic_novels', max_sources=500),
    )

# Roll daily view buckets older than the retention window into weekly buckets.
# Daily granularity only matters for the rolling 7-day display; older history
# is kept as one row per ISO week so the table doesn't grow forever.
@scheduler.register_task(interval=WEEK, name="consolidate_source_views")  # 7 days
def consolidate_source_views():
    """Run the consolidate_source_views command to roll old daily views into weekly buckets."""
    _run_job(
        "Starting consolidation of old daily view buckets...",
        "Daily view bucket consolidation completed successfully",
        "Error consolidating daily view buckets: {error}",
        lambda: call_command('consolidate_source_views'),
    )

# Top up the popular-source refresh queue. Runs often but queues at most one job
# per tick and skips sources refreshed in the last 6 days, so each source ends up
# updated about weekly while the batch always stays on a single crawler thread
# (even with several crawler replicas).
@scheduler.register_task(interval=HOUR, name="update_popular_sources")  # hourly
def update_popular_sources():
    """Queue the next update for the most popular sources."""
    _run_job(
        "Queueing next popular source update...",
        "Popular source update queue check completed",
        "Error queueing popular source update: {error}",
        lambda: call_command('update_popular_sources', top=20),
    )

# Progressively prune orphan novels, empty sources and dead-source duplicates.
# Bounded --limit per run so a 40k-novel first pass spreads over many runs.
@scheduler.register_task(interval=600, name="prune_library")
def prune_library_task():
    import os
    if os.getenv("LNCRAWL_PRUNE_APPLY", "1").lower() in ("0", "false", "no"):
        return
    _run_job(
        "Pruning library (bounded batch)...",
        "Library prune batch completed",
        "Error pruning library: {error}",
        lambda: call_command('prune_library', apply=True, limit=200),
    )

# Trim terminal Job rows so a continuously running harvest feeder cannot grow
# the job table without bound. Keeps jobs still referenced by queued candidates.
@scheduler.register_task(interval=DAY, name="prune_jobs")  # daily
def prune_jobs_task():
    _run_job(
        "Pruning old finished jobs...",
        "Old job prune completed",
        "Error pruning old jobs: {error}",
        lambda: call_command('prune_jobs'),
    )


@scheduler.register_task(interval=DAY, name="prune_epub_cache")  # daily
def prune_epub_cache_task():
    _run_job(
        "Pruning expired EPUB cache files...",
        "EPUB cache prune completed",
        "Error pruning EPUB cache: {error}",
        lambda: call_command('prune_epub_cache'),
    )

# Refresh the projected ranking columns that search sorts read. One set-based
# UPDATE; only rows whose values changed are written, so frequent runs are cheap.
@scheduler.register_task(interval=300, name="refresh_novel_rankings")  # 5 minutes
def refresh_novel_rankings_task():
    from .services.novel_rankings import refresh_novel_rankings

    logger.info("Refreshing novel ranking projections...")
    try:
        updated = refresh_novel_rankings()
        logger.info("Novel ranking refresh completed: %s row(s) updated", updated)
    except Exception as e:
        logger.error(f"Error refreshing novel rankings: {str(e)}", exc_info=True)
        raise  # Re-raise to mark task as failed

def start_scheduler():
    """Start the scheduler if it's not already running."""
    if not scheduler.running:
        scheduler.start()
