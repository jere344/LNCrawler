"""Move novel folders the DB does not know about back to the import folder.

The import flow (``run_import``) only ever moves into ``LNCRAWL_OUTPUT_PATH``;
nothing removes a library folder whose DB rows were dropped (fresh DB, a bad
merge, manual cleanup). Those folders are invisible to the app yet keep taking
space. This command walks the top level of the library and, for every folder
that no ``Novel`` (via ``novel_path``), ``NovelFromSource`` (via ``source_path``)
or ``NovelAlias`` refers to, moves it to ``IMPORT_FOLDER_PATH`` so a later
``run_import`` can register it again.

Moving is recoverable but still a filesystem change, so ``--apply`` is
required; the default only reports what would happen.
"""

import os
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from lncrawler_api.models import Novel, NovelAlias, NovelFromSource
from lncrawler_api.utils.lncrawler_paths import move_and_merge_directory


class Command(BaseCommand):
    help = (
        "Move library folders that are not registered in the DB to the import "
        "folder, so run_import can pick them up again."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually move the folders. Without it the command only reports (dry run).",
        )

    def handle(self, *args, **options):
        self.apply = options["apply"]
        root = settings.LNCRAWL_OUTPUT_PATH
        import_folder = settings.IMPORT_FOLDER_PATH
        if not root or not os.path.isdir(root):
            raise CommandError(f"LNCRAWL_OUTPUT_PATH is not a directory: {root}")
        if not import_folder:
            raise CommandError("IMPORT_FOLDER_PATH is not defined in settings")

        known = self._known_top_level_folders()
        mode = "APPLY" if self.apply else "DRY-RUN"
        self.stdout.write(self.style.WARNING(
            f"prune_unregistered ({mode}) root={root} import={import_folder}"
        ))

        moved = 0
        for name in sorted(os.listdir(root)):
            src = os.path.join(root, name)
            if name.startswith(".") or not os.path.isdir(src):
                continue
            if name in known or slugify(name) in known:
                continue

            target = os.path.join(import_folder, name)
            if not self.apply:
                self.stdout.write(f"  [DRY-RUN] would move {name!r} -> {target}")
            else:
                os.makedirs(import_folder, exist_ok=True)
                if os.path.exists(target):
                    move_and_merge_directory(src, target)
                else:
                    shutil.move(src, target)
                self.stdout.write(self.style.SUCCESS(f"  moved {name!r} -> {target}"))
            moved += 1

        self.stdout.write(self.style.SUCCESS(
            f"prune_unregistered: {moved} folder(s) "
            f"{'moved' if self.apply else 'would be moved'}"
        ))

    @staticmethod
    def _known_top_level_folders() -> set:
        """Top-level folder names any DB row points at (novel_path/source_path/alias)."""
        known = set()
        paths = list(Novel.objects.exclude(
            novel_path__isnull=True).values_list("novel_path", flat=True))
        paths += list(NovelFromSource.objects.exclude(
            source_path__isnull=True).values_list("source_path", flat=True))
        for path in paths:
            if path:
                known.add(path.split(os.sep, 1)[0])
        known.update(NovelAlias.objects.values_list("slug", flat=True))
        return known
