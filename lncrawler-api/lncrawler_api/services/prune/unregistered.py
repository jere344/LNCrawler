"""Phase 0: library folders no DB row points at."""

import os
import shutil

from django.conf import settings

from lncrawler_api.models import Job, Novel, NovelAlias
from lncrawler_api.services.folder_guard import ACTIVE_CRAWL_STATUSES
from lncrawler_api.utils.lncrawler_paths import move_and_merge_directory
from lncrawler_api.utils.slug import slugify


class UnregisteredFoldersMixin:
    def _phase_unregistered_folders(self):
        """Move library folders the DB does not know about back to the import folder.

        ``run_import`` only ever moves into the library; nothing removes a folder
        whose DB rows were dropped (fresh DB, bad merge, manual cleanup). Those
        folders are invisible to the app yet keep taking space. This is a
        filesystem sweep, so it ignores the cursor/--limit/--percent/--source
        knobs, but it only runs when ``--sweep-unregistered`` is passed (a folder
        with no row may belong to a download that is still in progress) and only
        moves when ``--apply`` is set.
        """
        import_folder = settings.IMPORT_FOLDER_PATH
        if not import_folder:
            self.stdout.write(self.style.ERROR(
                "IMPORT_FOLDER_PATH is not defined; skipping unregistered-folder sweep"
            ))
            return

        known = self._known_top_level_folders()
        crawling = self._crawling_folders()
        moved = 0
        for name in sorted(os.listdir(self.root)):
            src = os.path.join(self.root, name)
            if name.startswith(".") or not os.path.isdir(src):
                continue
            if name in known or slugify(name) in known:
                continue
            if name in crawling:
                # A crawl of a new novel writes here before its novel row exists.
                self.stdout.write(f"  skipped {name!r}: a crawl is writing into it")
                continue

            target = os.path.join(import_folder, name)
            if not self.apply:
                self.stdout.write(f"  [DRY-RUN] would move unregistered {name!r} -> {target}")
            else:
                os.makedirs(import_folder, exist_ok=True)
                if os.path.exists(target):
                    move_and_merge_directory(src, target)
                else:
                    shutil.move(src, target)
                self.stdout.write(self.style.SUCCESS(f"  moved unregistered {name!r} -> {target}"))
            moved += 1

        if moved:
            self.stdout.write(self.style.SUCCESS(
                f"  unregistered folders: {moved} "
                f"{'moved' if self.apply else 'would be moved'}"
            ))

    @staticmethod
    def _crawling_folders() -> set:
        """Top-level folder names an active crawl writes into (recorded in its selected_novel)."""
        folders = set()
        for selected in Job.objects.filter(status__in=ACTIVE_CRAWL_STATUSES).values_list("selected_novel", flat=True):
            folder = (selected or {}).get("folder")
            if folder:
                folders.add(folder)
        return folders

    @staticmethod
    def _known_top_level_folders() -> set:
        """Top-level folder names any DB row points at (novel_path/alias).

        A source folder lives inside its novel folder, so its top-level name is the novel's.
        """
        known = set()
        paths = list(Novel.objects.values_list("novel_path", flat=True))
        for path in paths:
            if path:
                known.add(path.split(os.sep, 1)[0])
        known.update(NovelAlias.objects.values_list("slug", flat=True))
        return known
