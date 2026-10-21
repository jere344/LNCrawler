from django.core.management.base import BaseCommand

from ...models import LLMRequest
from ...services import llm_service, llm_tasks


class Command(BaseCommand):
    help = (
        "Enqueue and process LLMRequest rows (see services/llm_tasks.py). "
        "Without a task, every task takes turns."
    )

    def add_arguments(self, parser):
        parser.add_argument("task", nargs="?", choices=sorted(llm_tasks.REGISTRY))
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Max requests to process this run (default: until the provider limits, "
                 "the daily budget or an empty queue stops it).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only enqueue and report pending rows; make no LLM call.",
        )

    def handle(self, *args, **options):
        task_name = options["task"]
        names = [task_name] if task_name else sorted(llm_tasks.REGISTRY)

        if options["dry_run"]:
            for name in names:
                created = llm_tasks._top_up(llm_tasks.REGISTRY[name], options["limit"])
                pending = LLMRequest.objects.filter(task=name, status=LLMRequest.STATUS_PENDING).count()
                self.stdout.write(f"{name}: enqueued {created}, pending {pending} (dry run, no LLM call)")
            return

        if not llm_service.is_configured():
            self.stdout.write(f"{task_name or 'queue'}: skipped (no LLM provider configured)")
            return

        counts = llm_tasks.run_queue([task_name] if task_name else None, options["limit"], stdout=self.stdout)
        self.stdout.write(f"{task_name or 'all tasks'}: {counts}")
