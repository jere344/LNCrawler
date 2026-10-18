from django.conf import settings
from django.core.management.base import BaseCommand

from ...models import LLMRequest
from ...services import llm_tasks


class Command(BaseCommand):
    help = "Enqueue and process LLMRequest rows for one LLM task (see services/llm_tasks.py)."

    def add_arguments(self, parser):
        parser.add_argument("task", choices=sorted(llm_tasks.REGISTRY))
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Max requests to process this run (default: the task's calls_per_tick).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only enqueue and report pending rows; make no LLM call.",
        )

    def handle(self, *args, **options):
        task_name = options["task"]
        task = llm_tasks.REGISTRY[task_name]
        limit = options["limit"] or task.calls_per_tick()

        if options["dry_run"]:
            created = task.enqueue(limit)
            pending = LLMRequest.objects.filter(task=task_name, status=LLMRequest.STATUS_PENDING).count()
            self.stdout.write(f"{task_name}: enqueued {created}, pending {pending} (dry run, no LLM call)")
            return

        if not settings.LLM_API_KEY:
            self.stdout.write(f"{task_name}: skipped (LLM_API_KEY not set)")
            return

        counts = llm_tasks.run_task(task_name, limit, stdout=self.stdout)
        self.stdout.write(f"{task_name}: {counts}")
