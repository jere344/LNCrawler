"""Queue a ``tag_r18`` candidate for each non-adult tag that has none yet.

Nothing is changed here: ``TagR18Task`` decides through the ``run_llm`` command. Re-running is safe: a tag that already has a candidate is skipped.
"""
from django.core.management.base import BaseCommand

from lncrawler_api.services.tag_r18_service import queue_r18_candidates

# A few thousand tags per run keeps the LLM queue bounded; the next run takes the rest.
DEFAULT_LIMIT = 2000


class Command(BaseCommand):
    help = "Queue tag_r18 candidates for non-adult tags that have none."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                            help="Queue at most this many tags per run (default %(default)s).")

    def handle(self, *args, **options):
        created = queue_r18_candidates(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"tag_r18 candidates: {created} new"))
