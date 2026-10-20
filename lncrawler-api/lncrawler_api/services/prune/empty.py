"""Phase 2: sources with no chapter content."""

from pathlib import Path

from django.db.models import Exists, OuterRef

from lncrawler_api.models import (
    Chapter,
    Comment,
    NovelFromSource,
    ReadingHistory,
    SourceVote,
)
from lncrawler_api.utils import chapter_utils


class EmptySourcesMixin:
    @staticmethod
    def _source_has_user_data(source) -> bool:
        if Comment.objects.filter(chapter__novel_from_source=source).exists():
            return True
        if ReadingHistory.objects.filter(source=source).exists():
            return True
        if SourceVote.objects.filter(source=source).exists():
            return True
        return False

    def _chapter_files_on_disk(self, base) -> bool:
        """Whether the source folder holds chapter files (loose json or archive)."""
        root = Path(base)
        if (root / "json.7z").is_file():
            return True
        json_dir = root / "json"
        return json_dir.is_dir() and any(json_dir.glob("*.json"))

    def _repair_has_content(self, source, base) -> bool:
        """Re-check the flagged chapters on disk; repair has_content only on --apply.

        Strict read: an archive that cannot be read raises ChapterReadError, so
        the caller keeps the source instead of treating it as empty.
        """
        pending = list(source.chapters.filter(has_content=False).values_list("pk", "chapter_id"))
        if not pending:
            return True  # every chapter already has content
        # One batch read; archived chapters are never extracted into the library.
        data = chapter_utils.read_chapters_no_extract(
            base, [cid for _, cid in pending], strict=True
        )
        repaired = [
            pk for pk, cid in pending
            if cid in data and chapter_utils.chapter_dict_has_content(data[cid])
        ]
        if repaired and self.apply:
            Chapter.objects.filter(pk__in=repaired).update(has_content=True)
        return bool(repaired)

    def _keep_reason(self, source):
        """Why a source flagged empty must be kept, or None when it may be deleted.

        ``has_content`` is a cached column written at import time, so an import
        that ran before the bodies landed leaves it False while the files are on
        disk. Deletion is destructive, so the files are re-checked first.
        """
        base = source.absolute_source_path
        if not base:
            return None
        if not source.chapters.exists():
            if self._chapter_files_on_disk(base):
                return "chapter files on disk but no rows"
            return None
        try:
            found = self._repair_has_content(source, base)
        except chapter_utils.ChapterReadError as exc:
            return f"unreadable ({exc})"
        return "content present on disk" if found else None

    def _phase_empty_sources(self):
        self.stdout.write("Phase 2: empty sources")
        empties = self._sample(
            NovelFromSource.objects.filter(
                ~Exists(Chapter.objects.filter(novel_from_source_id=OuterRef("pk"), has_content=True))
            )
            .filter(novel__created_at__lt=self.age_cutoff)
            .select_related("novel", "external_source"),
            field="novel_id",
        )
        examined, last_pk = 0, None
        for source in self._window(empties, "empty").iterator():
            last_pk = source.pk
            examined += 1
            keep = self._keep_reason(source)
            if keep:
                self.stdout.write(f"  KEEP source {source.id} {source.title!r}: {keep}")
                continue
            if not self.force and self._source_has_user_data(source):
                self.stdout.write(
                    f"  SKIP source {source.id} {source.title!r}: has user data"
                )
                continue
            self._delete_source_named(source, "empty source")
        self._advance("empty", last_pk, examined)
