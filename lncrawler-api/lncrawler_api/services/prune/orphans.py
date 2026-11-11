"""Phase 1: novels with no source left."""

from functools import partial

from django.db.models import Exists, OuterRef

from lncrawler_api.models import Novel, NovelFromSource
from lncrawler_api.services.folder_guard import FolderBusy
from lncrawler_api.services.novel_deletion import delete_novel
from lncrawler_api.services.novel_operations import file_journal

from .common import logger


def _user_data_counts(novel):
    """How many rows of user data a deletion of ``novel`` takes with it, by kind."""
    return {
        "bookmarks": novel.bookmarked_by_users.count(),
        "reviews": novel.reviews.count(),
        "comments": novel.comments.count(),
        "reading_list_items": novel.in_reading_lists.count(),
        "ratings": novel.ratings.count(),
    }


class OrphanNovelsMixin:
    def _phase_orphan_novels(self):
        """Delete novels that have no source, with their user data (bookmarks, reviews, lists, comments).

        A novel without a source is not readable anywhere: the same rule as deleting a novel's last
        source. Its folder goes to the prune trash, like the source folders of the other phases. The
        audit entry and the dry-run line count the user data that goes with each novel.
        """
        self.stdout.write("Phase 1: orphan novels")
        orphans = self._sample(
            Novel.objects.filter(
                ~Exists(NovelFromSource.objects.filter(novel_id=OuterRef("pk"))),
                created_at__lt=self.age_cutoff,
            )
        )
        examined, last_pk = 0, None
        for novel in self._window(orphans, "novel").iterator():
            last_pk = novel.pk
            examined += 1
            nid, ntitle = novel.id, str(novel)
            counts = _user_data_counts(novel)
            summary = ", ".join(f"{name} {count}" for name, count in counts.items())
            if not self.apply:
                self.stdout.write(
                    f"  [DRY-RUN] would delete novel {nid} {ntitle!r} (folder {novel.novel_path!r}; {summary})"
                )
            else:
                try:
                    with file_journal() as files:
                        trash_path = delete_novel(novel, trash=partial(self._move_to_trash, files=files), files=files)
                except FolderBusy:
                    self.stdout.write(f"  busy, novel {nid} {ntitle!r} kept for a later run")
                    continue
                except Exception as exc:
                    logger.error("prune_library: failed deleting novel %s: %s", nid, exc)
                    continue
                self._audit({
                    "kind": "novel",
                    "id": nid,
                    "title": ntitle,
                    "reason": "orphan",
                    "user_data": counts,
                    "trash_path": trash_path,
                })
                self.stdout.write(self.style.SUCCESS(f"  deleted novel {nid} {ntitle!r} ({summary})"))
            self.deleted += 1
            self._maybe_sleep()
        self._advance("novel", last_pk, examined)
