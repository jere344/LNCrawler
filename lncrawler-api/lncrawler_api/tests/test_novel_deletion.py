"""Deleting novels: the helper, deleting a novel's last source, prune orphans, admin deletes, merges."""

import json
import os
import time
from datetime import timedelta
from io import StringIO

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from ..admin.source_admin import ExternalSourceAdmin, NovelFromSourceAdmin
from ..management.commands.prune_library import Command
from ..models import (
    ExternalSource,
    Job,
    Novel,
    NovelAlias,
    NovelBookmark,
    NovelFromSource,
    Review,
)
from ..services.folder_guard import BUSY_MESSAGE, FolderBusy
from ..services.merge_service import merge_novels
from ..services.novel_deletion import after_source_deleted, delete_novel, sweep_stale_quarantine
from ..services.novel_operations import file_journal
from .helpers import MergeTestCase, bare_novel, make_source


class DeleteNovelTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.novel = bare_novel("lotm", "lotm")
        self.site_a = self.make_source(
            self.novel, ExternalSource.objects.create(source_name="site-a"),
            "LOTM", "http://a/lotm", "lotm", "site-a", 2,
        )
        self.site_b = self.make_source(
            self.novel, ExternalSource.objects.create(source_name="site-b"),
            "LOTM", "http://b/lotm", "lotm", "site-b", 1,
        )
        self.novel_dir = os.path.join(self.tmp, "lotm")
        # Django sets instance.pk to None on delete(): the assertions read the pks kept here.
        self.novel_pk = self.novel.pk
        self.source_pks = [self.site_a.pk, self.site_b.pk]

    def _exists(self, *parts):
        return os.path.exists(os.path.join(self.tmp, *parts))

    def test_removes_every_source_folder_and_the_novel_folder(self):
        with self.captureOnCommitCallbacks(execute=True):
            delete_novel(self.novel)

        self.assertFalse(Novel.objects.filter(pk=self.novel_pk).exists())
        self.assertFalse(NovelFromSource.objects.filter(pk__in=self.source_pks).exists())
        self.assertFalse(self._exists("lotm", "site-a"))
        self.assertFalse(self._exists("lotm", "site-b"))
        self.assertFalse(self._exists("lotm"))

    def test_folders_are_renamed_aside_at_once_and_removed_on_commit(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            delete_novel(self.novel)

        # The names are free at once; the renamed copies stay until the commit.
        self.assertFalse(self._exists("lotm", "site-a"))
        self.assertFalse(self._exists("lotm", "site-b"))
        self.assertEqual(len(_quarantined(self.tmp)), 3)  # both source folders and the novel folder
        self.assertTrue(callbacks)

        for callback in callbacks:
            callback()

        self.assertEqual(_quarantined(self.tmp), [])

    def test_rolled_back_delete_keeps_rows_and_files(self):
        class Boom(Exception):
            pass

        # The caller's journal spans its transaction: a rollback puts the renamed folders back.
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(Boom):
                with file_journal() as files:
                    with transaction.atomic():
                        delete_novel(self.novel, files=files)
                        raise Boom()

        self.assertTrue(Novel.objects.filter(pk=self.novel_pk).exists())
        self.assertEqual(NovelFromSource.objects.filter(novel_id=self.novel_pk).count(), 2)
        self.assertTrue(self._exists("lotm", "site-a"))
        self.assertTrue(self._exists("lotm", "site-b"))

    def test_busy_novel_raises_and_deletes_nothing(self):
        Job.objects.create(job_type=Job.JOB_TYPE_DOWNLOAD, status=Job.STATUS_DOWNLOADING, novel=self.novel)

        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(FolderBusy):
                delete_novel(self.novel)

        self.assertTrue(Novel.objects.filter(pk=self.novel.pk).exists())
        self.assertEqual(NovelFromSource.objects.filter(novel=self.novel).count(), 2)
        self.assertTrue(self._exists("lotm", "site-a"))

    def test_novel_folder_with_other_content_is_kept(self):
        with open(os.path.join(self.novel_dir, "notes.txt"), "w", encoding="utf-8") as fh:
            fh.write("not a leftover")

        with self.captureOnCommitCallbacks(execute=True):
            delete_novel(self.novel)

        self.assertFalse(self._exists("lotm", "site-a"))
        self.assertTrue(self._exists("lotm", "notes.txt"))

    def test_lock_and_cache_leftovers_do_not_keep_the_novel_folder(self):
        open(os.path.join(self.novel_dir, ".lncrawl.lock"), "w").close()
        os.makedirs(os.path.join(self.novel_dir, "epub_cache"))

        with self.captureOnCommitCallbacks(execute=True):
            delete_novel(self.novel)

        self.assertFalse(self._exists("lotm"))

    def test_folder_another_novel_row_names_is_kept(self):
        Novel.objects.create(slug="lotm-twin", novel_path="lotm")

        with self.captureOnCommitCallbacks(execute=True):
            delete_novel(self.novel)

        self.assertFalse(self._exists("lotm", "site-a"))
        self.assertTrue(self._exists("lotm"))

    def test_trash_callable_moves_a_sourceless_folder_instead_of_removing_it(self):
        orphan = bare_novel("ghost", "ghost")
        orphan_pk = orphan.pk
        os.makedirs(os.path.join(self.tmp, "ghost"))
        trashed = []

        with self.captureOnCommitCallbacks(execute=True):
            result = delete_novel(orphan, trash=lambda folder: trashed.append(folder) or "trash/ghost")

        self.assertEqual(trashed, ["ghost"])
        self.assertEqual(result, "trash/ghost")
        self.assertFalse(Novel.objects.filter(pk=orphan_pk).exists())


class AfterSourceDeletedTests(MergeTestCase):
    def test_deleting_the_last_source_through_the_source_admin_deletes_the_novel(self):
        novel = bare_novel("nfs", "nfs")
        novel_pk = novel.pk
        source = self.make_source(
            novel, ExternalSource.objects.create(source_name="nfs-site"),
            "NFS", "http://nfs/1", "nfs", "nfs-site", 1,
        )

        with self.captureOnCommitCallbacks(execute=True):
            NovelFromSourceAdmin(NovelFromSource, admin.site)._delete_source(source)

        self.assertFalse(Novel.objects.filter(pk=novel_pk).exists())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "nfs")))

    def test_deleting_a_non_last_source_refreshes_the_canonical_source(self):
        novel = bare_novel("two", "two")
        best = make_source(
            novel, external=ExternalSource.objects.create(source_name="two-a"),
            title="Best", source_url="http://two/a", upvotes=9,
        )
        other = make_source(
            novel, external=ExternalSource.objects.create(source_name="two-b"),
            title="Other", source_url="http://two/b",
        )
        novel.refresh_from_db()
        self.assertEqual(novel.canonical_source_id, best.pk)

        with self.captureOnCommitCallbacks(execute=True):
            NovelFromSourceAdmin(NovelFromSource, admin.site)._delete_source(best)

        novel.refresh_from_db()
        self.assertEqual(novel.canonical_source_id, other.pk)
        self.assertTrue(NovelFromSource.objects.filter(pk=other.pk).exists())

    def test_deleting_the_last_source_of_a_site_deletes_only_its_novel(self):
        gone_novel = bare_novel("gone", "gone")
        self.make_source(
            gone_novel, ExternalSource.objects.create(source_name="site-gone"),
            "Gone", "http://gone/1", "gone", "site-gone", 1,
        )
        kept_novel = bare_novel("kept", "kept")
        kept_gone = self.make_source(
            kept_novel, ExternalSource.objects.create(source_name="site-kept-gone"),
            "Kept", "http://kept/gone", "kept", "site-kept-gone", 1,
        )
        self.make_source(
            kept_novel, ExternalSource.objects.create(source_name="site-kept"),
            "Kept", "http://kept/other", "kept", "site-kept", 1,
        )

        with self.captureOnCommitCallbacks(execute=True):
            ExternalSourceAdmin(ExternalSource, admin.site)._delete_with_sources(kept_gone.external_source)
            ExternalSourceAdmin(ExternalSource, admin.site)._delete_with_sources(
                gone_novel.sources.get().external_source
            )

        self.assertFalse(Novel.objects.filter(pk=gone_novel.pk).exists())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "gone")))
        self.assertTrue(Novel.objects.filter(pk=kept_novel.pk).exists())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "kept", "site-kept-gone")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "kept", "site-kept")))

    def test_prune_deleting_the_last_source_trashes_the_novel_folder(self):
        novel = bare_novel("pr", "pr")
        source = self.make_source(
            novel, ExternalSource.objects.create(source_name="prsite"),
            "PR", "http://pr/1", "pr", "prsite", 1,
        )
        cmd = _prune_command(self.tmp)
        cmd.apply = True

        self.assertTrue(cmd._delete_source_named(source, "test"))

        self.assertFalse(Novel.objects.filter(pk=novel.pk).exists())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "pr")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, ".prune_trash", "pr", "prsite")))
        with open(os.path.join(self.tmp, ".prune_trash", "audit.jsonl"), encoding="utf-8") as fh:
            entries = [json.loads(line) for line in fh]
        self.assertEqual([entry["kind"] for entry in entries], ["source", "novel"])
        self.assertEqual(entries[1]["id"], str(novel.pk))
        self.assertIsNotNone(entries[1]["trash_path"])

    def test_after_source_deleted_keeps_a_novel_that_still_has_a_source(self):
        novel = bare_novel("keep", "keep")
        self.make_source(
            novel, ExternalSource.objects.create(source_name="keep-site"),
            "Keep", "http://keep/1", "keep", "keep-site", 1,
        )

        self.assertIsNone(after_source_deleted(novel.pk))
        self.assertTrue(Novel.objects.filter(pk=novel.pk).exists())

    def test_non_last_source_of_a_busy_novel_is_kept_with_its_folder(self):
        novel = bare_novel("busy-two", "busy-two")
        first = self.make_source(
            novel, ExternalSource.objects.create(source_name="bt-a"),
            "BT", "http://bt/a", "busy-two", "bt-a", 1,
        )
        self.make_source(
            novel, ExternalSource.objects.create(source_name="bt-b"),
            "BT", "http://bt/b", "busy-two", "bt-b", 1,
        )
        Job.objects.create(job_type=Job.JOB_TYPE_DOWNLOAD, status=Job.STATUS_DOWNLOADING, novel=novel)

        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(FolderBusy):
                NovelFromSourceAdmin(NovelFromSource, admin.site)._delete_source(first)

        self.assertEqual(NovelFromSource.objects.filter(novel=novel).count(), 2)
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "busy-two", "bt-a")))

    def test_busy_novel_in_a_site_deletion_rolls_back_the_sources_already_deleted(self):
        site = ExternalSource.objects.create(source_name="shared-site")
        free = bare_novel("site-free", "site-free")
        free_source = self.make_source(free, site, "F", "http://sf/1", "site-free", "shared-site", 1)
        busy = bare_novel("site-busy", "site-busy")
        busy_source = self.make_source(busy, site, "B", "http://sb/1", "site-busy", "shared-site", 1)
        Job.objects.create(job_type=Job.JOB_TYPE_DOWNLOAD, status=Job.STATUS_DOWNLOADING, novel=busy)

        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(FolderBusy):
                ExternalSourceAdmin(ExternalSource, admin.site)._delete_with_sources(site)

        self.assertTrue(NovelFromSource.objects.filter(pk=free_source.pk).exists())
        self.assertTrue(NovelFromSource.objects.filter(pk=busy_source.pk).exists())
        self.assertTrue(ExternalSource.objects.filter(pk=site.pk).exists())
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "site-free", "shared-site")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "site-busy", "shared-site")))


class AdminBulkDeleteTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.superuser = get_user_model().objects.create_superuser("deleter", "d@example.com", "pw")
        self.client.force_login(self.superuser)
        self.free = bare_novel("free", "free")
        self.make_source(
            self.free, ExternalSource.objects.create(source_name="free-site"),
            "Free", "http://free/1", "free", "free-site", 1,
        )
        self.busy = bare_novel("busy", "busy")
        self.make_source(
            self.busy, ExternalSource.objects.create(source_name="busy-site"),
            "Busy", "http://busy/1", "busy", "busy-site", 1,
        )
        Job.objects.create(job_type=Job.JOB_TYPE_DOWNLOAD, status=Job.STATUS_DOWNLOADING, novel=self.busy)

    def test_bulk_delete_skips_the_busy_novel_and_shows_the_message(self):
        url = reverse("admin:lncrawler_api_novel_changelist")
        response = self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [self.free.pk, self.busy.pk],
                "post": "yes",
            },
            follow=True,
        )

        self.assertContains(response, BUSY_MESSAGE)
        self.assertFalse(Novel.objects.filter(pk=self.free.pk).exists())
        self.assertTrue(Novel.objects.filter(pk=self.busy.pk).exists())
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "busy", "busy-site")))

    def test_single_delete_of_a_busy_novel_shows_the_message(self):
        url = reverse("admin:lncrawler_api_novel_delete", args=[self.busy.pk])
        response = self.client.post(url, {"post": "yes"}, follow=True)

        self.assertContains(response, BUSY_MESSAGE)
        self.assertTrue(Novel.objects.filter(pk=self.busy.pk).exists())


class OrphanPruneTests(MergeTestCase):
    def test_orphan_novel_with_user_data_is_deleted(self):
        novel = bare_novel("ghost", "ghost")
        Novel.objects.filter(pk=novel.pk).update(created_at=timezone.now() - timedelta(days=8))
        os.makedirs(os.path.join(self.tmp, "ghost"))
        user = get_user_model().objects.create_user(username="fan", password="x")
        NovelBookmark.objects.create(user=user, novel=novel)
        Review.objects.create(novel=novel, user=user, title="Nice", content="!", rating=4)

        call_command("prune_library", "--apply", verbosity=0)

        self.assertFalse(Novel.objects.filter(pk=novel.pk).exists())
        self.assertFalse(NovelBookmark.objects.filter(novel_id=novel.pk).exists())
        self.assertFalse(Review.objects.filter(novel_id=novel.pk).exists())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "ghost")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, ".prune_trash", "ghost")))

    def test_audit_and_dry_run_count_the_user_data_and_the_trash_path(self):
        novel = bare_novel("counted", "counted")
        Novel.objects.filter(pk=novel.pk).update(created_at=timezone.now() - timedelta(days=8))
        os.makedirs(os.path.join(self.tmp, "counted"))
        user = get_user_model().objects.create_user(username="counter", password="x")
        NovelBookmark.objects.create(user=user, novel=novel)
        Review.objects.create(novel=novel, user=user, title="A", content="b", rating=3)

        dry = StringIO()
        call_command("prune_library", stdout=dry)
        self.assertIn("bookmarks 1, reviews 1, comments 0, reading_list_items 0, ratings 0", dry.getvalue())
        self.assertTrue(Novel.objects.filter(pk=novel.pk).exists())

        call_command("prune_library", "--apply", verbosity=0)

        with open(os.path.join(self.tmp, ".prune_trash", "audit.jsonl"), encoding="utf-8") as fh:
            entry = [json.loads(line) for line in fh if '"orphan"' in line][-1]
        self.assertEqual(entry["user_data"], {
            "bookmarks": 1, "reviews": 1, "comments": 0, "reading_list_items": 0, "ratings": 0,
        })
        self.assertTrue(os.path.isdir(entry["trash_path"]))

    def test_orphan_novel_is_kept_on_a_dry_run(self):
        novel = bare_novel("ghost", "ghost")
        Novel.objects.filter(pk=novel.pk).update(created_at=timezone.now() - timedelta(days=8))

        call_command("prune_library", verbosity=0)

        self.assertTrue(Novel.objects.filter(pk=novel.pk).exists())


class MergeKeepsTargetTests(MergeTestCase):
    def test_simple_merge_deletes_the_source_novel_and_keeps_the_target(self):
        target = bare_novel("target", "target")
        self.make_source(
            target, ExternalSource.objects.create(source_name="t-site"),
            "Target", "http://t/1", "target", "t-site", 1,
        )
        source = bare_novel("incoming", "incoming")
        source_pk = source.pk
        self.make_source(
            source, ExternalSource.objects.create(source_name="i-site"),
            "Incoming", "http://i/1", "incoming", "i-site", 1,
        )

        with self.captureOnCommitCallbacks(execute=True):
            merge_novels(source, target)

        self.assertFalse(Novel.objects.filter(pk=source_pk).exists())
        self.assertEqual(target.sources.count(), 2)
        target.refresh_from_db()
        self.assertIsNotNone(target.canonical_source_id)

    def test_dedupe_of_the_targets_only_copy_keeps_the_target(self):
        # The target's only source is the duplicate that the incoming copy replaces: the target is
        # empty for a moment, until the winner moves in. It must survive.
        target = bare_novel("same", "same")
        weaker = self.make_source(
            target, ExternalSource.objects.create(source_name="same-a"),
            "Same", "http://same/1", "same", "same-a", 1,
        )
        incoming_novel = bare_novel("same-b", "same-b")
        incoming_pk = incoming_novel.pk
        stronger = self.make_source(
            incoming_novel, ExternalSource.objects.create(source_name="same-b-site"),
            "Same", "http://same/1", "same-b", "same-b-site", 3,
        )

        with self.captureOnCommitCallbacks(execute=True):
            merge_novels(incoming_novel, target)

        self.assertTrue(Novel.objects.filter(pk=target.pk).exists())
        self.assertFalse(Novel.objects.filter(pk=incoming_pk).exists())
        self.assertEqual(list(target.sources.values_list("pk", flat=True)), [stronger.pk])
        self.assertFalse(NovelFromSource.objects.filter(pk=weaker.pk).exists())
        target.refresh_from_db()
        self.assertEqual(target.canonical_source_id, stronger.pk)
        self.assertTrue(NovelAlias.objects.filter(slug="same-b", novel=target).exists())


def _quarantined(parent):
    """The ``.deleting-*`` folders waiting in ``parent``."""
    return [name for name in os.listdir(parent) if name.startswith(".deleting-")]


def _prune_command(root):
    """A prune command with the attributes the phases read, as the tests of the prune module set them."""
    cmd = Command()
    cmd.apply = False
    cmd.limit = 0
    cmd.percent = 100
    cmd.force = False
    cmd.sleep = 0
    cmd.samples = 6
    cmd.max_shift = 5
    cmd.threshold = 0.90
    cmd.min_chapters = 0
    cmd.recheck = False
    cmd.source_filter = None
    cmd.verdicts = {}
    cmd.root = root
    cmd.trash_root = os.path.join(root, ".prune_trash")
    cmd.examined = 0
    cmd.kept_phase3 = 0
    cmd.deleted = 0
    cmd.cursor = {}
    cmd.cursor_scope = "-|100"
    cmd.age_cutoff = timezone.now() - timedelta(days=7)
    cmd.stdout = StringIO()
    return cmd


class StaleQuarantineSweepTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.quarantine = os.path.join(self.tmp, ".deleting-old")
        self.kept_source = os.path.join(self.tmp, "lotm", "site-a")
        for folder in (self.quarantine, self.kept_source):
            os.makedirs(folder)
        self.two_days_later = time.time() + 2 * 24 * 3600

    def test_removes_stale_quarantine_at_the_root(self):
        self.assertEqual(sweep_stale_quarantine(now=self.two_days_later), 1)

        self.assertFalse(os.path.exists(self.quarantine))
        self.assertTrue(os.path.isdir(self.kept_source))

    def test_keeps_quarantine_younger_than_a_day(self):
        self.assertEqual(sweep_stale_quarantine(now=time.time()), 0)

        self.assertTrue(os.path.isdir(self.quarantine))

    def test_ignores_files_and_folders_below_the_root(self):
        stray_file = os.path.join(self.tmp, ".deleting-file")
        open(stray_file, "w").close()
        nested = os.path.join(self.kept_source, ".deleting-nested")
        os.makedirs(nested)

        self.assertEqual(sweep_stale_quarantine(now=self.two_days_later), 1)

        self.assertTrue(os.path.isfile(stray_file))
        self.assertTrue(os.path.isdir(nested))
