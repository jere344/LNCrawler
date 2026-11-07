"""Stored chapter stats on NovelFromSource: the refresh writer and the admin hooks that call it."""

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.db import DatabaseError
from django.test import RequestFactory, TestCase

from ..admin.chapter_admin import ChapterAdmin
from ..models import Chapter
from ..services import chapter_stats
from ..services.chapter_stats import refresh_chapter_stats
from .helpers import make_novel, make_source


def add_chapters(source, flags, first_id=1):
    """One chapter per entry of ``flags`` (its has_content), numbered from ``first_id``."""
    return [
        Chapter.objects.create(
            novel_from_source=source,
            chapter_id=number,
            url=f"{source.source_url}/{number}",
            title=f"Chapter {number}",
            has_content=has_content,
        )
        for number, has_content in enumerate(flags, start=first_id)
    ]


def stats(source):
    """(chapters_count, available_chapters_count, first pk, latest pk) as stored on the row."""
    source.refresh_from_db()
    return (
        source.chapters_count,
        source.available_chapters_count,
        source.first_available_chapter_id,
        source.latest_available_chapter_id,
    )


class RefreshChapterStatsTests(TestCase):
    def setUp(self):
        self.source = make_source(make_novel("Gaps", "gaps"))
        self.other = make_source(make_novel("Other", "other"))

    def test_counts_and_first_latest_skip_chapters_without_content(self):
        chapters = add_chapters(self.source, [True, False, True, False, False])

        refresh_chapter_stats([self.source.pk])

        self.assertEqual(
            stats(self.source),
            (5, 2, chapters[0].pk, chapters[2].pk),
        )

    def test_first_and_latest_follow_chapter_id_not_insert_order(self):
        ten = Chapter.objects.create(novel_from_source=self.source, chapter_id=10, url="u10", title="10", has_content=True)
        two = Chapter.objects.create(novel_from_source=self.source, chapter_id=2, url="u2", title="2", has_content=True)
        Chapter.objects.create(novel_from_source=self.source, chapter_id=7, url="u7", title="7", has_content=False)

        refresh_chapter_stats([self.source.pk])

        self.assertEqual(stats(self.source), (3, 2, two.pk, ten.pk))

    def test_source_whose_chapters_were_all_deleted_resets_to_zero(self):
        add_chapters(self.source, [True, True])
        refresh_chapter_stats([self.source.pk])

        # The FKs go NULL with their chapters (SET_NULL); the counts only the refresh resets.
        Chapter.objects.filter(novel_from_source=self.source).delete()
        refresh_chapter_stats([self.source.pk])

        self.assertEqual(stats(self.source), (0, 0, None, None))

    def test_returns_and_writes_only_the_rows_that_changed(self):
        add_chapters(self.source, [True])
        add_chapters(self.other, [False])
        ids = [self.source.pk, self.other.pk]

        self.assertEqual(refresh_chapter_stats(ids), 2)
        self.assertEqual(refresh_chapter_stats(ids), 0)

        add_chapters(self.source, [True], first_id=2)
        self.assertEqual(refresh_chapter_stats(ids), 1)

    def test_batches_over_every_source_when_no_ids_are_given(self):
        sources = [make_source(make_novel(f"Batch {i}", f"batch-{i}")) for i in range(5)]
        for count, source in enumerate(sources, start=1):
            add_chapters(source, [True] * count)

        # The two empty sources of setUp are unchanged, so only the five are written.
        self.assertEqual(refresh_chapter_stats(batch_size=2), 5)

        for count, source in enumerate(sources, start=1):
            self.assertEqual(stats(source)[:2], (count, count))

    def test_skip_locked_pass_writes_the_same_stats(self):
        # Not a real lock test: holding a row lock from a second connection needs
        # a non-test-transaction setup, so only the code path runs here.
        add_chapters(self.source, [True, False])

        self.assertEqual(refresh_chapter_stats(skip_locked=True, batch_size=1), 1)
        self.assertEqual(stats(self.source)[:2], (2, 1))

    def test_a_failing_batch_is_skipped_and_the_rest_still_refresh(self):
        first = make_source(make_novel("First", "first"))
        second = make_source(make_novel("Second", "second"))
        add_chapters(first, [True])
        add_chapters(second, [True, True])
        real = chapter_stats.refresh_chapter_stats_sql
        calls = []

        def flaky(cursor, source_ids=None):
            calls.append(list(source_ids))
            if len(calls) == 1:
                raise DatabaseError("simulated failure")
            return real(cursor, source_ids)

        with patch.object(chapter_stats, "refresh_chapter_stats_sql", side_effect=flaky):
            updated = refresh_chapter_stats([first.pk, second.pk], batch_size=1)

        self.assertEqual(len(calls), 2)
        self.assertEqual(updated, 1)
        self.assertEqual(stats(first)[:2], (0, 0))
        self.assertEqual(stats(second)[:2], (2, 2))


class ChapterAdminStatsTests(TestCase):
    def setUp(self):
        self.admin = ChapterAdmin(Chapter, AdminSite())
        self.request = RequestFactory().post("/")
        self.old = make_source(make_novel("Old", "old"))
        self.new = make_source(make_novel("New", "new"))
        self.first, self.moved = add_chapters(self.old, [True, True])
        refresh_chapter_stats([self.old.pk, self.new.pk])

    def test_reassigning_a_chapter_refreshes_both_sources(self):
        self.moved.novel_from_source = self.new
        self.admin.save_model(self.request, self.moved, form=None, change=True)

        self.assertEqual(stats(self.old), (1, 1, self.first.pk, self.first.pk))
        self.assertEqual(stats(self.new), (1, 1, self.moved.pk, self.moved.pk))

    def test_adding_a_chapter_refreshes_its_source(self):
        added = Chapter(novel_from_source=self.old, chapter_id=3, url="u3", title="3", has_content=True)
        self.admin.save_model(self.request, added, form=None, change=False)

        self.assertEqual(stats(self.old), (3, 3, self.first.pk, added.pk))

    def test_deleting_a_chapter_refreshes_its_source(self):
        self.admin.delete_model(self.request, self.moved)

        self.assertEqual(stats(self.old), (1, 1, self.first.pk, self.first.pk))

    def test_bulk_delete_refreshes_every_affected_source(self):
        new_first, new_second = add_chapters(self.new, [True, True])
        refresh_chapter_stats([self.new.pk])

        self.admin.delete_queryset(
            self.request, Chapter.objects.filter(pk__in=[self.moved.pk, new_first.pk]),
        )

        self.assertEqual(stats(self.old), (1, 1, self.first.pk, self.first.pk))
        self.assertEqual(stats(self.new), (1, 1, new_second.pk, new_second.pk))
