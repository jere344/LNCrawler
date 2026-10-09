"""Tests for the scheduler."""

from django.test import TestCase


class SchedulerOrphanTaskTests(TestCase):
    def test_orphan_task_rows_are_removed(self):
        from ..scheduler import scheduler
        from ..models import ScheduledTask

        ScheduledTask.get_or_create_task("calculate_similarities", 604800)
        ScheduledTask.get_or_create_task("ghost_task", 60)

        scheduler._remove_orphan_tasks()

        self.assertFalse(ScheduledTask.objects.filter(name="ghost_task").exists())
        self.assertTrue(
            ScheduledTask.objects.filter(name="calculate_similarities").exists()
        )
