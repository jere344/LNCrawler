"""Flag novel sources that carry an R18 tag as adult.

Tag flags are applied on import, on admin changes and on merges. Run this after
bulk tag edits made outside those paths. It only sets is_adult to True; flags
set for other reasons are never cleared.
"""

from django.core.management.base import BaseCommand

from ...models.sources_models import recompute_adult_sources


class Command(BaseCommand):
    help = "Set is_adult on sources linked to an R18-flagged tag (never clears flags)."

    def handle(self, *args, **options):
        count = recompute_adult_sources()
        self.stdout.write(f"Flagged {count} novel source(s) as adult from R18 tags.")
