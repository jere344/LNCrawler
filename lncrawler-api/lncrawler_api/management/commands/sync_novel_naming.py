"""
Make each novel's slug and folder follow its canonical source (services/novel_naming.py).

The scheduled task does this every 5 minutes, at most 5 folder renames per run. This command runs
the same sync by hand, e.g. to drain a backlog with ``--limit``. ``--dry-run`` lists the planned
canonical changes, renames and collisions without changing anything (it does not apply ``--limit``).
The command runs whether or not NOVEL_NAMING_SYNC_ENABLED is set.
"""

from django.core.management.base import BaseCommand, CommandError

from ...services.novel_naming import DEFAULT_RENAME_LIMIT, sync_novel_naming


class Command(BaseCommand):
    help = "Apply the canonical source of each novel: recompute it, then rename the folders that no longer match."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List the planned changes and collisions without changing anything.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=DEFAULT_RENAME_LIMIT,
            help=f"Folder renames attempted in this run (default {DEFAULT_RENAME_LIMIT}). Ignored by --dry-run.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 1:
            raise CommandError("--limit must be at least 1")
        sync_novel_naming(limit=options["limit"], dry_run=options["dry_run"], stdout=self.stdout)
