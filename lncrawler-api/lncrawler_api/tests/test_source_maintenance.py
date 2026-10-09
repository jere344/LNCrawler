"""Tests for pruning and source view maintenance."""

import os
import shutil
import tempfile
from datetime import date, timedelta

from django.contrib.auth import get_user_model

from django.core.management import call_command

from django.test import TestCase, override_settings

from django.utils import timezone

from ..models import (
    Comment,
    ExternalSource,
    Job,
    Novel,
    NovelFromSource,
    ReadingHistory,
    SourceVote,
    WeeklySourceView,
)
from .helpers import MergeTestCase

from .helpers import MergeTestCase


class PruneLibraryPortTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.novel = Novel.objects.create(
            title="Story", slug="story", novel_path="story"
        )
        dead_ext = ExternalSource.objects.create(source_name="deadsite")
        live_ext = ExternalSource.objects.create(source_name="livesite")
        self.dead = self.make_source(
            self.novel, dead_ext, "S", "http://dead/s", "story", "deadsite", 2
        )
        self.keeper = self.make_source(
            self.novel, live_ext, "S", "http://live/s", "story", "livesite", 3
        )
        self.dead_chapter = self.dead.chapters.order_by("chapter_id").first()
        self.keeper_chapter = self.keeper.chapters.order_by("chapter_id").first()

    def test_port_user_data_moves_comments_history_and_votes(self):
        from ..management.commands.prune_library import Command

        user = get_user_model().objects.create_user(username="reader", password="x")
        comment = Comment.objects.create(
            chapter=self.dead_chapter, author_name="anon", message="hi"
        )
        ReadingHistory.objects.create(
            user=user, novel=self.novel, source=self.dead,
            last_read_chapter=self.dead_chapter,
        )
        SourceVote.objects.create(source=self.dead, ip_address="1.1.1.1", vote_type="up")
        # Same voter already voted on the keeper: the duplicate must be dropped.
        SourceVote.objects.create(
            source=self.keeper, ip_address="1.1.1.1", vote_type="down"
        )

        Command()._port_user_data(self.dead, self.keeper)

        comment.refresh_from_db()
        self.assertEqual(comment.chapter, self.keeper_chapter)
        history = ReadingHistory.objects.get(user=user)
        self.assertEqual(history.source, self.keeper)
        # Progress marker must follow the history, or the chapter deletion nulls it.
        self.assertEqual(history.last_read_chapter, self.keeper_chapter)
        self.assertEqual(self.keeper.votes.count(), 1)
        self.keeper.refresh_from_db()
        self.assertEqual((self.keeper.upvotes, self.keeper.downvotes), (0, 1))
        self.novel.refresh_from_db()
        self.assertEqual(self.novel.comment_count, 1)

    def test_port_user_data_applies_chapter_shift(self):
        from ..management.commands.prune_library import Command

        # Simulate the dead source prepending an intro chapter: dead position 0
        # really matches keeper position 1, so the shift from _content_similarity
        # is +1 and chapter-keyed data must follow it.
        keeper_second = self.keeper.chapters.order_by("chapter_id")[1]
        user = get_user_model().objects.create_user(username="shifted", password="x")
        comment = Comment.objects.create(
            chapter=self.dead_chapter, author_name="anon", message="hi"
        )
        ReadingHistory.objects.create(
            user=user, novel=self.novel, source=self.dead,
            last_read_chapter=self.dead_chapter,
        )

        Command()._port_user_data(self.dead, self.keeper, shift=1)

        comment.refresh_from_db()
        self.assertEqual(comment.chapter, keeper_second)
        self.assertEqual(
            ReadingHistory.objects.get(user=user).last_read_chapter, keeper_second
        )

    def test_sample_percent_uses_md5_bucket_subset(self):
        import hashlib
        import uuid as uuidlib

        from ..management.commands.prune_library import Command

        for _ in range(30):
            Novel.objects.create(
                title="Sample", slug=uuidlib.uuid4().hex, novel_path="sample"
            )

        cmd = Command()
        cmd.percent = 50
        sampled = set(cmd._sample(Novel.objects.all()).values_list("id", flat=True))
        all_ids = set(Novel.objects.values_list("id", flat=True))

        threshold = int(50 / 100 * 256)
        for nid in all_ids:
            bucket = int(hashlib.md5(str(nid).encode()).hexdigest()[:2], 16)
            self.assertEqual(nid in sampled, bucket < threshold)

        self.assertTrue(sampled)
        self.assertLess(len(sampled), len(all_ids))

        cmd.percent = 100
        self.assertEqual(cmd._sample(Novel.objects.all()).count(), Novel.objects.count())

    def test_empty_source_with_stale_flag_is_rechecked_on_disk(self):
        from io import StringIO

        from ..management.commands.prune_library import Command

        Novel.objects.filter(pk=self.novel.pk).update(
            created_at=timezone.now() - timedelta(days=8)
        )
        # Simulate a stale flag: files are on disk but the column says empty.
        self.dead.chapters.update(has_content=False)

        cmd = Command()
        cmd.apply = False
        cmd.limit = 0
        cmd.percent = 100
        cmd.force = False
        cmd.age_cutoff = timezone.now() - timedelta(days=7)
        cmd.deleted = 0
        cmd.examined = 0
        cmd.stdout = StringIO()

        cmd._phase_empty_sources()

        self.assertEqual(cmd.deleted, 0)
        self.assertTrue(NovelFromSource.objects.filter(pk=self.dead.pk).exists())
        self.assertIn("content present on disk", cmd.stdout.getvalue())
        self.assertFalse(self.dead.chapters.filter(has_content=False).exists())

    def test_window_pages_all_candidates_then_wraps(self):
        import uuid as uuidlib

        from ..management.commands.prune_library import Command

        for _ in range(4):
            Novel.objects.create(
                title="Paged", slug=uuidlib.uuid4().hex, novel_path="paged"
            )

        cmd = Command()
        cmd.limit = 2
        cmd.percent = 100
        cmd.examined = 0
        cmd.cursor_scope = "-|100"
        cmd.cursor = {}
        cmd._save_cursor = lambda: None

        seen = []
        while True:
            batch = list(cmd._window(Novel.objects.all(), "novel"))
            if not batch:
                break
            seen.extend(n.pk for n in batch)
            cmd._advance("novel", batch[-1].pk, len(batch))
            if cmd._cursor_key("novel") not in cmd.cursor:
                break

        self.assertEqual(len(seen), Novel.objects.count())
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(cmd.examined, len(seen))


class PruneUnregisteredTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-prune-unreg-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.imports = tempfile.mkdtemp(prefix="lncrawl-prune-imports-")
        self.addCleanup(shutil.rmtree, self.imports, True)
        for name, value in (
            ("LNCRAWL_OUTPUT_PATH", self.tmp),
            ("IMPORT_FOLDER_PATH", self.imports),
        ):
            override = override_settings(**{name: value})
            override.enable()
            self.addCleanup(override.disable)

        self.registered = Novel.objects.create(
            title="Kept", slug="kept", novel_path="kept"
        )
        os.makedirs(os.path.join(self.tmp, "kept", "site"))
        NovelFromSource.objects.create(
            novel=self.registered,
            external_source=ExternalSource.objects.create(source_name="site"),
            title="Kept",
            source_url="http://x/kept",
            source_path=os.path.join("kept", "site"),
        )
        os.makedirs(os.path.join(self.tmp, "orphan"))

    def test_unregistered_folder_moved_to_imports(self):
        call_command("prune_library", "--apply", "--sweep-unregistered", verbosity=0)

        self.assertFalse(os.path.exists(os.path.join(self.tmp, "orphan")))
        self.assertTrue(os.path.isdir(os.path.join(self.imports, "orphan")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "kept", "site")))

    def test_dry_run_changes_nothing(self):
        call_command("prune_library", "--sweep-unregistered", verbosity=0)

        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "orphan")))
        self.assertFalse(os.path.exists(os.path.join(self.imports, "orphan")))


class ConsolidateSourceViewsTests(TestCase):
    def setUp(self):
        novel = Novel.objects.create(title="Old", slug="old", novel_path="old")
        ext = ExternalSource.objects.create(source_name="site")
        self.source = NovelFromSource.objects.create(
            novel=novel, external_source=ext, title="Old", source_url="http://x/old"
        )

    def test_old_daily_views_roll_into_weekly_buckets(self):
        today = date.today()
        monday = today - timedelta(days=today.isoweekday() - 1) - timedelta(weeks=5)

        WeeklySourceView.objects.create(
            source=self.source, granularity=WeeklySourceView.DAY, day=monday, views=3
        )
        WeeklySourceView.objects.create(
            source=self.source,
            granularity=WeeklySourceView.DAY,
            day=monday + timedelta(days=1),
            views=4,
        )
        recent = WeeklySourceView.objects.create(
            source=self.source, granularity=WeeklySourceView.DAY, day=today, views=5
        )

        call_command("consolidate_source_views")

        weekly = WeeklySourceView.objects.get(
            source=self.source, granularity=WeeklySourceView.WEEK, day=monday
        )
        self.assertEqual(weekly.views, 7)
        self.assertFalse(
            WeeklySourceView.objects.filter(
                source=self.source,
                granularity=WeeklySourceView.DAY,
                day__lt=today - timedelta(days=WeeklySourceView.CONSOLIDATION_DAYS),
            ).exists()
        )
        recent.refresh_from_db()
        self.assertEqual(recent.views, 5)

    def test_consolidation_is_idempotent(self):
        today = date.today()
        monday = today - timedelta(days=today.isoweekday() - 1) - timedelta(weeks=5)
        WeeklySourceView.objects.create(
            source=self.source, granularity=WeeklySourceView.DAY, day=monday, views=3
        )

        call_command("consolidate_source_views")
        call_command("consolidate_source_views")

        weekly = WeeklySourceView.objects.get(
            source=self.source, granularity=WeeklySourceView.WEEK, day=monday
        )
        self.assertEqual(weekly.views, 3)


class UpdatePopularSourcesTests(TestCase):
    def _make_source(self, novel_title, slug, source_name, url, views, updated=None):
        novel = Novel.objects.create(title=novel_title, slug=slug, novel_path=slug)
        external = ExternalSource.objects.create(source_name=source_name)
        return NovelFromSource.objects.create(
            novel=novel,
            external_source=external,
            title=novel_title,
            source_url=url,
            source_path=f"{slug}/{source_name}",
            source_slug=source_name,
            total_views=views,
            last_chapter_update=updated,
        )

    def test_queues_next_most_popular_stale_source(self):
        popular = self._make_source("Popular", "popular", "src-a", "http://a/1", 100)
        self._make_source("Unpopular", "unpopular", "src-b", "http://b/1", 1)

        call_command("update_popular_sources", top=1)

        job = Job.objects.get()
        self.assertEqual(job.job_type, Job.JOB_TYPE_DOWNLOAD)
        self.assertEqual(job.status, Job.STATUS_CREATED)
        self.assertEqual(job.target_url, popular.source_url)

    def test_queues_only_one_job_per_run(self):
        self._make_source("A", "a", "src-a", "http://a/1", 100)
        self._make_source("B", "b", "src-b", "http://b/1", 50)

        call_command("update_popular_sources", top=20)

        self.assertEqual(Job.objects.count(), 1)

    def test_skips_sources_updated_in_the_last_6_days(self):
        self._make_source(
            "Fresh", "fresh", "src-a", "http://a/1", 100,
            updated=timezone.now() - timedelta(days=2),
        )
        stale = self._make_source(
            "Stale", "stale", "src-b", "http://b/1", 50,
            updated=timezone.now() - timedelta(days=8),
        )

        call_command("update_popular_sources", top=20)

        job = Job.objects.get()
        self.assertEqual(job.target_url, stale.source_url)

    def test_waits_while_an_update_is_in_flight(self):
        # A second stale source exists, but the command must not queue it while
        # the first update is still running (single-thread guarantee).
        self._make_source("A", "a", "src-a", "http://a/1", 100)
        self._make_source("B", "b", "src-b", "http://b/1", 50)
        Job.objects.create(
            job_type=Job.JOB_TYPE_DOWNLOAD,
            query="Weekly popular source update",
            target_url="http://a/1",
            status=Job.STATUS_DOWNLOADING,
        )

        call_command("update_popular_sources", top=20)

        self.assertEqual(Job.objects.count(), 1)

    def test_skips_source_whose_last_job_failed(self):
        failed = self._make_source("Failed", "failed", "src-a", "http://a/1", 100)
        works = self._make_source("Works", "works", "src-b", "http://b/1", 50)
        Job.objects.create(
            job_type=Job.JOB_TYPE_DOWNLOAD,
            query="Weekly popular source update",
            target_url=failed.source_url,
            status=Job.STATUS_FAILED,
        )

        call_command("update_popular_sources", top=20)

        queued = Job.objects.get(status=Job.STATUS_CREATED)
        self.assertEqual(queued.target_url, works.source_url)
