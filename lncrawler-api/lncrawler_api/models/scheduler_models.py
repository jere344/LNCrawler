from django.db import models, transaction
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger('lncrawler_api')


class ScheduledTask(models.Model):
    """
    Model to store scheduled tasks with database-level locking to prevent 
    multiple workers from executing the same task simultaneously.
    """
    TASK_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    name = models.CharField(max_length=100, unique=True, help_text="Unique name for the task")
    interval_seconds = models.PositiveIntegerField(help_text="Task interval in seconds")
    last_run_at = models.DateTimeField(null=True, blank=True, help_text="Last successful execution time")
    next_run_at = models.DateTimeField(help_text="Next scheduled execution time")
    status = models.CharField(max_length=20, choices=TASK_STATUS_CHOICES, default='pending')
    locked_until = models.DateTimeField(null=True, blank=True, help_text="Lock expiration time to prevent zombie locks")
    worker_id = models.CharField(max_length=50, null=True, blank=True, help_text="ID of worker that locked this task")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(blank=True, help_text="Error message if task failed")
    
    class Meta:
        db_table = 'scheduler_scheduled_task'
        ordering = ['next_run_at']
    
    def __str__(self):
        return f"{self.name} (next: {self.next_run_at}, status: {self.status})"
    
    @classmethod
    def acquire_lock(cls, task_name: str, worker_id: str, lock_timeout_minutes: int = 30):
        """
        Try to acquire a lock on a task using database-level atomic operations.
        Returns the task instance if lock was acquired, None otherwise.
        """
        lock_until = timezone.now() + timedelta(minutes=lock_timeout_minutes)
        now = timezone.now()
        
        with transaction.atomic():
            try:
                # Try to get a task that's ready to run and is not currently held
                # by a live worker (never locked, or the previous lock expired).
                task = cls.objects.select_for_update(nowait=True).get(
                    models.Q(name=task_name, next_run_at__lte=now),
                    models.Q(locked_until__isnull=True) | models.Q(locked_until__lte=now),
                )
                
                # Lock the task
                task.status = 'running'
                task.locked_until = lock_until
                task.worker_id = worker_id
                task.save()
                
                logger.info(f"Task '{task_name}' locked by worker '{worker_id}' until {lock_until}")
                return task
                
            except cls.DoesNotExist:
                # Task doesn't exist, is not ready, or is already locked
                return None
            except Exception as e:
                logger.warning(f"Failed to acquire lock for task '{task_name}': {str(e)}")
                return None
    
    def heartbeat(self, lock_timeout_minutes: int = 30) -> bool:
        """
        Extend this task's lock while it is still running, so a long task is not
        reclaimed by another worker. Returns False if the lock is no longer ours.
        """
        updated = ScheduledTask.objects.filter(
            pk=self.pk, status='running', worker_id=self.worker_id
        ).update(locked_until=timezone.now() + timedelta(minutes=lock_timeout_minutes))
        return bool(updated)
    
    def release_lock(self, success: bool = True, error_message: str = "", no_github: bool = False):
        """
        Release the lock on this task and schedule next run. Only the worker that
        currently owns the lock may release it, so a worker whose lock was
        reclaimed after a stall cannot clobber the new owner.

        ``no_github`` suppresses the auto-issue for expected failures (a stale
        lock reclaimed after a restart), while genuine task errors still report.
        """
        worker_id = self.worker_id
        now = timezone.now()
        fields = {
            'locked_until': None,
            'worker_id': None,
            'updated_at': now,
        }
        if success:
            fields.update(
                status='completed',
                last_run_at=now,
                next_run_at=now + timedelta(seconds=self.interval_seconds),
                error_message="",
            )
        else:
            fields.update(
                status='failed',
                error_message=error_message,
                # Still schedule next run even if failed (tasks should retry)
                next_run_at=now + timedelta(seconds=self.interval_seconds),
            )
        
        updated = ScheduledTask.objects.filter(
            pk=self.pk, status='running', worker_id=worker_id
        ).update(**fields)
        
        if not updated:
            logger.warning(
                f"Task '{self.name}': release ignored, lock no longer held by worker '{worker_id}'"
            )
            return
        if success:
            logger.info(f"Task '{self.name}' completed successfully")
        else:
            logger.error(
                f"Task '{self.name}' failed: {error_message}",
                extra={"no_github": True} if no_github else None,
            )
    
    @classmethod
    def cleanup_stale_locks(cls, stale_timeout_minutes: int = 60):
        """
        Clean up stale locks (tasks that have been locked for too long, probably due to worker crashes).
        """
        cutoff_time = timezone.now() - timedelta(minutes=stale_timeout_minutes)
        stale_tasks = cls.objects.filter(
            status='running',
            locked_until__lt=cutoff_time
        )
        
        count = 0
        for task in stale_tasks:
            logger.warning(f"Cleaning up stale lock for task '{task.name}' (locked by worker '{task.worker_id}')")
            task.release_lock(
                success=False,
                error_message="Lock expired - worker may have crashed",
                no_github=True,
            )
            count += 1
        
        if count > 0:
            logger.info(f"Cleaned up {count} stale task locks")
    
    @classmethod
    def get_or_create_task(cls, name: str, interval_seconds: int):
        """
        Get or create a scheduled task with the given name and interval.
        """
        task, created = cls.objects.get_or_create(
            name=name,
            defaults={
                'interval_seconds': interval_seconds,
                # Due immediately so a new task (or a scheduler that was down)
                # runs on the next poll instead of waiting a full interval.
                'next_run_at': timezone.now(),
                'status': 'pending'
            }
        )
        
        if created:
            logger.info(f"Created new scheduled task: {name} (interval: {interval_seconds}s)")
        else:
            # Update interval if it changed
            if task.interval_seconds != interval_seconds:
                task.interval_seconds = interval_seconds
                task.save()
                logger.info(f"Updated interval for task {name}: {interval_seconds}s")
        
        return task
