"""Folder guard: crawls register on their novel, movers lock it, writers never recreate a folder."""

import os
import shutil
import threading
import time
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.urls import reverse
from django.test import TransactionTestCase
from django.utils import timezone

from ..management.commands.prune_epub_cache import Command as PruneEpubCache
from ..models import Candidate, ExternalSource, Job, Novel, NovelFromSource
from ..services import candidate_service, llm_tasks
from ..services.covers import overview
from ..services.downloader_service import DownloaderService
from ..services.folder_guard import BUSY_MESSAGE, FolderBusy, locked, locked_move, register_crawl
from ..services.merge_service import merge_novels
from ..services.split_service import move_sources, split_novel
from ..services.novel_operations import FileJournal, FileOperationError, file_journal
from ..services.epub_service import _build_lock
from ..utils.chapter_utils import source_lock
from ..utils.crawler_path import ensure_crawler_on_path
from ..utils.folders import make_subfolders
from .helpers import MergeTestCase, bare_novel

ensure_crawler_on_path()
from lncrawl.core import downloader  # noqa: E402

ACTIVE_STATUSES = (
    Job.STATUS_CREATED,
    Job.STATUS_SEARCHING,
    Job.STATUS_SEARCH_COMPLETED,
    Job.STATUS_DOWNLOADING,
)


def make_job(status=Job.STATUS_DOWNLOADING, novel=None):
    return Job.objects.create(job_type=Job.JOB_TYPE_DOWNLOAD, status=status, novel=novel)


class LockedMoveTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.novel = bare_novel("lotm", "lotm")
        self.make_source(
            self.novel, ExternalSource.objects.create(source_name="site-a"),
            "LOTM", "http://a/lotm", "lotm", "site-a", 1,
        )

    def test_active_crawl_blocks_the_move(self):
        for status in ACTIVE_STATUSES:
            with self.subTest(status=status):
                job = make_job(status, self.novel)
                with self.assertRaises(FolderBusy):
                    with locked_move(self.novel):
                        self.fail("the block must not run while a crawl is active")
                job.delete()

    def test_finished_crawl_does_not_block(self):
        for status in (Job.STATUS_DOWNLOAD_COMPLETED, Job.STATUS_FAILED):
            with self.subTest(status=status):
                job = make_job(status, self.novel)
                with locked_move(self.novel):
                    pass
                job.delete()

    def test_register_crawl_sets_job_novel_and_then_blocks_moves(self):
        job = make_job(novel=None)
        self.assertTrue(register_crawl(job, self.novel))
        job.refresh_from_db()
        self.assertEqual(job.novel_id, self.novel.pk)
        with self.assertRaises(FolderBusy):
            with locked_move(self.novel):
                pass

    def test_register_crawl_on_a_missing_novel_returns_false(self):
        job = make_job(novel=None)
        ghost = Novel(pk=987654321, slug="ghost", novel_path="ghost")
        self.assertFalse(register_crawl(job, ghost))
        job.refresh_from_db()
        self.assertIsNone(job.novel_id)

    def test_exception_inside_locked_move_undoes_disk_and_database(self):
        old = os.path.join(self.tmp, "lotm")
        new = os.path.join(self.tmp, "renamed")
        with self.assertRaises(RuntimeError):
            with locked_move(self.novel):
                with file_journal() as files:
                    with transaction.atomic():
                        files.move(old, new)
                        self.novel.novel_path = "renamed"
                        self.novel.save(update_fields=["novel_path"])
                        raise RuntimeError("boom")
        self.assertTrue(os.path.isdir(os.path.join(old, "site-a")))
        self.assertFalse(os.path.exists(new))
        self.novel.refresh_from_db()
        self.assertEqual(self.novel.novel_path, "lotm")

    def test_merge_is_refused_while_a_crawl_of_the_target_is_active(self):
        target = bare_novel("lom", "lom")
        self.make_source(
            target, ExternalSource.objects.create(source_name="site-b"),
            "LOM", "http://b/lom", "lom", "site-b", 1,
        )
        make_job(novel=target)
        with self.assertRaises(FolderBusy):
            merge_novels(self.novel, target)
        self.assertTrue(Novel.objects.filter(pk=self.novel.pk).exists())
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "lotm", "site-a")))

    def test_consolidation_succeeds_while_another_crawl_of_the_novel_is_active(self):
        # Consolidation adds a source folder inside the novel folder; it does not move the
        # novel folder, so a crawl of another source of the same novel must not block it.
        crawl_dir = os.path.join(self.tmp, "lotm", "site-b")
        os.makedirs(crawl_dir)
        make_job(novel=self.novel)
        source_dir, folder = NovelFromSource._consolidate_source_directory(
            source_dir=crawl_dir, output_path=self.tmp, novel=self.novel,
            existing_source=None, title="LOTM",
        )
        self.assertEqual(folder, "site-b")
        self.assertTrue(os.path.isdir(source_dir))

    def test_locked_does_not_check_for_crawls(self):
        crawl = make_job(novel=self.novel)
        with locked(self.novel):
            # The crawl is still active and still registered: locked() only holds the row.
            self.assertTrue(Job.objects.filter(pk=crawl.pk, novel=self.novel, status=Job.STATUS_DOWNLOADING).exists())

    def test_deleted_novel_makes_locked_move_busy_and_locked_raise(self):
        ghost = Novel(pk=987654321, slug="ghost", novel_path="ghost")
        with self.assertRaises(FolderBusy):
            with locked_move(ghost):
                self.fail("the block must not run for a deleted novel")
        with self.assertRaises(Novel.DoesNotExist):
            with locked(ghost):
                self.fail("the block must not run for a deleted novel")

    def test_file_journal_move_does_not_create_a_missing_parent(self):
        src = os.path.join(self.tmp, "lotm")
        with self.assertRaises(FileOperationError):
            FileJournal().move(src, os.path.join(self.tmp, "gone", "lotm"))
        self.assertTrue(os.path.isdir(src))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "gone")))

    def test_register_existing_source_registers_on_its_novel(self):
        source = NovelFromSource.objects.get(novel=self.novel)
        job = make_job(novel=None)
        DownloaderService._register_existing_source(job, source.pk)
        job.refresh_from_db()
        self.assertEqual(job.novel_id, self.novel.pk)


class CaseOnlyRenameTests(MergeTestCase):
    def test_same_folder_case_only_rename_does_not_trash_the_destination(self):
        # On NTFS "Foo" and "foo" are one folder: the destination exists and is the source.
        # Linux is case-sensitive, so the same-folder answer is simulated with samefile.
        src = os.path.join(self.tmp, "Foo")
        dst = os.path.join(self.tmp, "foo")
        os.mkdir(src)
        Path(src, "chapter.json").write_text("{}")
        os.mkdir(dst)
        with mock.patch("os.path.samefile", return_value=True):
            FileJournal().move(src, dst)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".trash")))
        self.assertTrue(os.path.isfile(os.path.join(dst, "chapter.json")))
        self.assertFalse(os.path.exists(src))


class WritersWithOutdatedPathTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.novel = bare_novel("lotm", "lotm")
        self.source = self.make_source(
            self.novel, ExternalSource.objects.create(source_name="site-a"),
            "LOTM", "http://a/lotm", "lotm", "site-a", 1,
        )

    def test_source_lock_raises_and_does_not_recreate_the_folder(self):
        missing = os.path.join(self.tmp, "gone", "site")
        with self.assertRaises(FileNotFoundError):
            with source_lock(missing):
                self.fail("the lock must not be taken on a missing folder")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "gone")))

    def test_chapter_write_raises_and_does_not_recreate_the_folder(self):
        missing = os.path.join(self.tmp, "gone", "site")
        with self.assertRaises(FileNotFoundError):
            downloader._write_chapter_json(
                missing, Path(missing) / "json" / "00001.json", {"title": "x"},
            )
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "gone")))

    def test_cover_overview_fails_and_does_not_recreate_the_folder(self):
        folder = os.path.join(self.tmp, "lotm", "site-a")
        shutil.rmtree(folder)
        self.assertFalse(overview.generate_overview(self.source))
        self.assertFalse(os.path.exists(folder))

    def test_audiobook_upload_folder_is_not_recreated_under_a_missing_source(self):
        missing = os.path.join(self.tmp, "gone", "site")
        with self.assertRaises(FileNotFoundError):
            make_subfolders(missing, "audio", "part-001", "g1")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "gone")))

    def test_upload_folder_is_created_under_an_existing_source(self):
        make_subfolders(self.source.absolute_source_path, "audio", "part-001", "g1")
        self.assertTrue(os.path.isdir(os.path.join(self.source.absolute_source_path, "audio", "part-001", "g1")))

    def test_epub_build_lock_raises_on_a_missing_cache_folder(self):
        dest = os.path.join(self.tmp, "gone", "site", "epub_cache", "book.epub")
        with self.assertRaises(FileNotFoundError):
            with _build_lock(dest):
                self.fail("the lock must not be taken on a missing folder")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "gone")))


class LockFilesAreKeptTests(MergeTestCase):
    def test_prune_epub_cache_never_deletes_a_lock_file(self):
        cache = os.path.join(self.tmp, "lotm", "site-a", "epub_cache")
        os.makedirs(cache)
        lock = os.path.join(cache, "book.epub.lock")
        Path(lock).write_text("")
        two_hours_ago = time.time() - 7200
        os.utime(lock, (two_hours_ago, two_hours_ago))
        command = PruneEpubCache()
        command.count, command.bytes, command.dry_run = 0, 0, False
        command._prune_file(lock, "book.epub.lock", time.time(), 7 * 24 * 3600)
        self.assertTrue(os.path.exists(lock))
        self.assertEqual(command.count, 0)


class LockedRowTests(TransactionTestCase):
    """Two connections: the row lock of one transaction is seen by the other.

    The holding thread waits on an event with a timeout, so a failing test cannot hang.
    """

    def setUp(self):
        self.novel = bare_novel("held", "held")

    def _hold_row(self, holding, release):
        def hold():
            try:
                with transaction.atomic():
                    Novel.objects.select_for_update().filter(pk=self.novel.pk).first()
                    holding.set()
                    release.wait(timeout=10)
            finally:
                connection.close()

        thread = threading.Thread(target=hold, daemon=True)
        thread.start()
        return thread

    def test_row_held_by_another_transaction_raises_folder_busy_at_once(self):
        holding, release = threading.Event(), threading.Event()
        thread = self._hold_row(holding, release)
        try:
            self.assertTrue(holding.wait(timeout=10))
            started = time.monotonic()
            with self.assertRaises(FolderBusy):
                with locked_move(self.novel):
                    self.fail("the block must not run while another transaction holds the row")
            self.assertLess(time.monotonic() - started, 5)
        finally:
            release.set()
            thread.join(timeout=10)

    def test_register_crawl_waits_for_a_running_move(self):
        holding, release = threading.Event(), threading.Event()
        thread = self._hold_row(holding, release)
        timer = threading.Timer(0.5, release.set)
        try:
            self.assertTrue(holding.wait(timeout=10))
            timer.start()
            job = make_job(novel=None)
            started = time.monotonic()
            self.assertTrue(register_crawl(job, self.novel))
            self.assertGreaterEqual(time.monotonic() - started, 0.3)
            job.refresh_from_db()
            self.assertEqual(job.novel_id, self.novel.pk)
        finally:
            timer.cancel()
            release.set()
            thread.join(timeout=10)


class MergeRetryTests(MergeTestCase):
    """A busy novel makes the LLM merge retry later: no attempt is spent, no review, no failure."""

    def setUp(self):
        super().setUp()
        self.first = bare_novel("alpha", "alpha")
        self.second = bare_novel("beta", "beta")

    def test_folder_busy_is_released_for_a_later_run(self):
        token = timezone.now()
        candidate = Candidate.objects.create(
            kind=llm_tasks.NovelMergeTask.name,
            target_ids=[str(self.first.pk), str(self.second.pk)],
            target_names=["Alpha", "Beta"],
            signature="folder-guard-retry",
            status=Candidate.STATUS_PENDING,
            claimed_at=token,
        )
        task = llm_tasks.REGISTRY[llm_tasks.NovelMergeTask.name]
        judgement = {"answer": "yes", "confidence": 0.99, "reason": ""}
        counts = {"done": 0, "failed": 0, "retry": 0, "rate_limited": False}
        with mock.patch.object(llm_tasks.NovelMergeTask, "apply_change", side_effect=FolderBusy()):
            llm_tasks._settle_two_phase(task, candidate.pk, token, judgement, None, counts, None)

        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_PENDING)
        self.assertEqual(candidate.attempts, 0)
        self.assertIsNone(candidate.claimed_at)
        self.assertGreater(candidate.not_before, timezone.now() + timedelta(minutes=1))
        self.assertEqual(counts["retry"], 1)
        self.assertEqual(counts["failed"], 0)


class BusyMessageTests(MergeTestCase):
    """A busy novel reaches the people who asked for the change as a message, not a crash."""

    def setUp(self):
        super().setUp()
        self.duplicate = bare_novel("lom", "lom")
        self.make_source(
            self.duplicate, ExternalSource.objects.create(source_name="site-a"),
            "LOM", "http://a/lom", "lom", "site-a", 1,
        )
        self.target = bare_novel("lotm", "lotm")
        self.make_source(
            self.target, ExternalSource.objects.create(source_name="site-b"),
            "LOTM", "http://b/lotm", "lotm", "site-b", 1,
        )
        self.admin = get_user_model().objects.create_superuser(username="admin", password="x")
        self.client.force_login(self.admin)

    def test_admin_merge_shows_the_busy_message_and_moves_nothing(self):
        make_job(novel=self.target)
        url = reverse("admin:lncrawler_api_novel_merge")
        response = self.client.post(
            url,
            {"source_novel": self.duplicate.pk, "target_novel": self.target.pk, "confirm": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, BUSY_MESSAGE)
        self.assertTrue(Novel.objects.filter(pk=self.duplicate.pk).exists())
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "lom", "site-a")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "lotm", "site-a")))

    def test_candidate_apply_raises_candidate_error_with_the_busy_message(self):
        token = timezone.now()
        candidate = Candidate.objects.create(
            kind=llm_tasks.NovelMergeTask.name,
            target_ids=[str(self.duplicate.pk), str(self.target.pk)],
            target_names=["Lom", "LOTM"],
            signature="folder-guard-busy-apply",
            status=Candidate.STATUS_REVIEW,
            verdict={"answer": "yes", "confidence": 0.99, "reason": ""},
        )
        with mock.patch.object(llm_tasks.NovelMergeTask, "apply_change", side_effect=FolderBusy()):
            with self.assertRaises(candidate_service.CandidateError) as raised:
                candidate_service.apply_candidate(candidate)
        self.assertEqual(str(raised.exception), BUSY_MESSAGE)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, Candidate.STATUS_REVIEW)
        self.assertIsNone(candidate.claimed_at)
        self.assertTrue(Novel.objects.filter(pk=self.duplicate.pk).exists())


class SplitAndMoveBusyTests(MergeTestCase):
    """A busy novel refuses a split or a move before anything changes on disk or in the rows."""

    def setUp(self):
        super().setUp()
        self.novel = bare_novel("lotm", "lotm")
        self.first = self.make_source(
            self.novel, ExternalSource.objects.create(source_name="site-a"),
            "LOTM", "http://a/lotm", "lotm", "site-a", 1,
        )
        self.second = self.make_source(
            self.novel, ExternalSource.objects.create(source_name="site-b"),
            "LOTM B", "http://b/lotm", "lotm", "site-b", 1,
        )
        self.target = bare_novel("lom", "lom")
        self.make_source(
            self.target, ExternalSource.objects.create(source_name="site-c"),
            "LOM", "http://c/lom", "lom", "site-c", 1,
        )

    def _assert_nothing_moved(self):
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "lotm", "site-b")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "moved-away")))
        self.assertFalse(Novel.objects.filter(slug="moved-away").exists())
        self.second.refresh_from_db()
        self.assertEqual(self.second.novel_id, self.novel.pk)

    def test_split_refuses_while_the_novel_has_an_active_crawl(self):
        make_job(novel=self.novel)
        with self.assertRaises(FolderBusy):
            split_novel(self.novel, [self.second], new_slug="moved-away")
        self._assert_nothing_moved()

    def test_move_sources_refuses_while_the_target_has_an_active_crawl(self):
        make_job(novel=self.target)
        with self.assertRaises(FolderBusy):
            move_sources(self.novel, [self.second], self.target)
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "lotm", "site-b")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "lom", "site-b")))
        self.second.refresh_from_db()
        self.assertEqual(self.second.novel_id, self.novel.pk)
