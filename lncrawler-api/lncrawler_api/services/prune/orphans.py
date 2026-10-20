"""Phase 1: novels with no source left."""

from django.db import transaction
from django.db.models import Exists, OuterRef

from lncrawler_api.models import Novel, NovelFromSource

from .common import logger


class OrphanNovelsMixin:
    def _novel_has_user_data(self, novel) -> bool:
        try:
            if novel.comments.exists():
                return True
            if novel.bookmarked_by_users.exists():
                return True
            if novel.ratings.exists():
                return True
            if novel.reading_histories.exists():
                return True
            if novel.in_reading_lists.exists():
                return True
        except Exception:
            # A missing reverse relation must never crash the prune run.
            return True
        return False

    def _phase_orphan_novels(self):
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
            if not self.force and self._novel_has_user_data(novel):
                self.stdout.write(f"  SKIP novel {novel.id} {novel.title!r}: has user data")
                continue
            if not self.apply:
                self.stdout.write(f"  [DRY-RUN] would delete novel {novel.id} {novel.title!r}")
            else:
                try:
                    with transaction.atomic():
                        nid, ntitle = novel.id, novel.title
                        novel.delete()
                        self._audit({"kind": "novel", "id": nid, "title": ntitle, "reason": "orphan"})
                    self.stdout.write(self.style.SUCCESS(f"  deleted novel {nid} {ntitle!r}"))
                except Exception as exc:
                    logger.error("prune_library: failed deleting novel %s: %s", novel.id, exc)
                    continue
            self.deleted += 1
            self._maybe_sleep()
        self._advance("novel", last_pk, examined)
