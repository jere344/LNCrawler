"""Tests for the scheduler."""

from unittest import mock

from django.test import TestCase, override_settings

from .llm_helpers import llm_chain


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


class SchedulerLLMGateTests(TestCase):
    @override_settings(**llm_chain("ollama", api_key=""))
    def test_keyless_provider_is_not_skipped(self):
        from .. import scheduler as scheduler_module

        with mock.patch.object(scheduler_module, "call_command") as call:
            scheduler_module.run_llm_queue_task()

        call.assert_called_once_with("run_llm")
