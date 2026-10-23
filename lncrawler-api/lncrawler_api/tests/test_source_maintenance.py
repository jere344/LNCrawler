"""Tests for pruning and source view maintenance."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model

from django.core.management import call_command

from django.test import TestCase, override_settings

from django.utils import timezone

from ..models import (
    Chapter,
    Comment,
    ExternalSource,
    Job,
    Novel,
    NovelFromSource,
    ReadingHistory,
    SourceVote,
    WeeklySourceView,
)
from ..management.commands.prune_library import Command
from ..services.prune.common import normalize_source_name
from ..utils import chapter_utils
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

        cmd = Command()
        cmd.force = False
        cmd._port_user_data(self.dead, self.keeper)

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

        cmd = Command()
        cmd.force = False
        cmd._port_user_data(self.dead, self.keeper, shift=1)

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
        cmd.apply = True
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


def _ensure_crawler_path():
    crawler_path = str(Path(settings.BASE_DIR).parent / "lncrawler-crawler")
    if crawler_path not in sys.path:
        sys.path.insert(0, crawler_path)


def _fake_crawler(name, hosts, is_disabled=False, disable_reason=None):
    return type(
        name,
        (),
        {
            "source_name": name,
            "base_url": [f"https://{host}/" for host in hosts],
            "is_disabled": is_disabled,
            "disable_reason": disable_reason,
        },
    )


class PruneHandledSourcesTests(TestCase):
    def _handled(self, classes):
        _ensure_crawler_path()
        with patch("lncrawl.core.sources.crawler_list", classes), \
                patch("lncrawl.core.sources.load_sources"):
            return Command()._load_handled_sources()

    def test_disabled_crawler_is_not_handled(self):
        alive = _fake_crawler("alive.com", ["alive.com"])
        dead = _fake_crawler("dead.com", ["dead.com"], is_disabled=True)

        handled = self._handled([alive, dead])

        self.assertIn("alive.com", handled)
        self.assertNotIn("dead.com", handled)

    def test_disable_reason_alone_excludes_crawler(self):
        alive = _fake_crawler("alive.com", ["alive.com"])
        reasoned = _fake_crawler("reasoned.com", ["reasoned.com"], disable_reason="x")

        handled = self._handled([alive, reasoned])

        self.assertIn("alive.com", handled)
        self.assertNotIn("reasoned.com", handled)

    def test_host_shared_with_enabled_crawler_stays_handled(self):
        disabled = _fake_crawler("old.com", ["shared.com"], is_disabled=True)
        enabled = _fake_crawler("new.com", ["shared.com"])

        handled = self._handled([disabled, enabled])

        self.assertIn("shared.com", handled)
        self.assertIn("new.com", handled)
        self.assertNotIn("old.com", handled)


class PruneFindKeepersTests(MergeTestCase):
    def _ext_names(self):
        return {
            ext.id: normalize_source_name(ext.source_name)
            for ext in ExternalSource.objects.all()
        }

    def test_keeper_with_equal_chapter_count_is_accepted(self):
        novel = Novel.objects.create(title="Equal", slug="equal", novel_path="equal")
        dead_ext = ExternalSource.objects.create(source_name="deadsite")
        live_ext = ExternalSource.objects.create(source_name="livesite")
        dead = self.make_source(novel, dead_ext, "E", "http://dead/e", "equal", "deadsite", 2)
        live = self.make_source(novel, live_ext, "E", "http://live/e", "equal", "livesite", 2)

        keepers = Command()._find_keepers(dead, {"livesite"}, self._ext_names())

        self.assertEqual(keepers, [live])

    def test_keeper_with_fewer_chapters_is_rejected(self):
        novel = Novel.objects.create(title="Short", slug="short", novel_path="short")
        dead_ext = ExternalSource.objects.create(source_name="deadsite")
        live_ext = ExternalSource.objects.create(source_name="livesite")
        dead = self.make_source(novel, dead_ext, "S", "http://dead/s", "short", "deadsite", 2)
        self.make_source(novel, live_ext, "S", "http://live/s", "short", "livesite", 1)

        keepers = Command()._find_keepers(dead, {"livesite"}, self._ext_names())

        self.assertEqual(keepers, [])


def _fake_7z_extract(members):
    """Stand-in for ``subprocess.run`` that writes the requested members.

    ``members`` maps archive member paths to raw bytes. Only the members that
    were asked for and exist in the map are written under the ``-o`` dir.
    """
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        out = next(arg[2:] for arg in cmd if arg.startswith("-o"))
        for arg in cmd:
            if arg.startswith("json/") and arg in members:
                dest = os.path.join(out, arg)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as fh:
                    fh.write(members[arg])
        return subprocess.CompletedProcess(cmd, 0)

    return fake_run, calls


class ReadChaptersNoExtractTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-read-noextract-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        open(os.path.join(self.tmp, "json.7z"), "wb").close()

    def _member(self, number, body="<p>hi</p>"):
        return json.dumps({"title": f"c{number}", "body": body}).encode("utf-8")

    def test_batch_reads_missing_chapters_with_one_subprocess_call(self):
        fake_run, calls = _fake_7z_extract({
            "json/00001.json": self._member(1),
            "json/00002.json": self._member(2),
        })
        with patch("subprocess.run", side_effect=fake_run):
            result = chapter_utils.read_chapters_no_extract(self.tmp, [1, 2])

        self.assertEqual(result, {1: {"title": "c1", "body": "<p>hi</p>"},
                                  2: {"title": "c2", "body": "<p>hi</p>"}})
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            [arg for arg in calls[0] if arg.startswith("json/")],
            ["json/00001.json", "json/00002.json"],
        )

    def test_member_absent_from_archive_is_left_out(self):
        fake_run, _ = _fake_7z_extract({"json/00001.json": self._member(1)})
        with patch("subprocess.run", side_effect=fake_run):
            result = chapter_utils.read_chapters_no_extract(self.tmp, [1, 3])

        self.assertEqual(set(result), {1})

    def test_invalid_json_member_is_skipped(self):
        fake_run, _ = _fake_7z_extract({
            "json/00001.json": self._member(1),
            "json/00002.json": b"{not json",
        })
        with patch("subprocess.run", side_effect=fake_run):
            result = chapter_utils.read_chapters_no_extract(self.tmp, [1, 2])

        self.assertEqual(set(result), {1})

    def test_chapters_already_on_disk_skip_subprocess(self):
        json_dir = os.path.join(self.tmp, "json")
        os.makedirs(json_dir)
        with open(os.path.join(json_dir, "00001.json"), "w", encoding="utf-8") as fh:
            json.dump({"title": "disk", "body": "x"}, fh)
        fake_run, calls = _fake_7z_extract({"json/00002.json": self._member(2)})

        with patch("subprocess.run", side_effect=fake_run):
            result = chapter_utils.read_chapters_no_extract(self.tmp, [1])

        self.assertEqual(result, {1: {"title": "disk", "body": "x"}})
        self.assertEqual(calls, [])

    def test_mixed_disk_and_archive_uses_one_call_for_missing_only(self):
        json_dir = os.path.join(self.tmp, "json")
        os.makedirs(json_dir)
        with open(os.path.join(json_dir, "00001.json"), "w", encoding="utf-8") as fh:
            json.dump({"title": "disk"}, fh)
        fake_run, calls = _fake_7z_extract({
            "json/00002.json": self._member(2),
            "json/00003.json": self._member(3),
        })

        with patch("subprocess.run", side_effect=fake_run):
            result = chapter_utils.read_chapters_no_extract(self.tmp, [1, 2, 3])

        self.assertEqual(set(result), {1, 2, 3})
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            [arg for arg in calls[0] if arg.startswith("json/")],
            ["json/00002.json", "json/00003.json"],
        )

    def test_real_7z_batch_reads_without_extracting(self):
        if not shutil.which("7z"):
            self.skipTest("7z not available")

        os.remove(os.path.join(self.tmp, "json.7z"))
        json_dir = os.path.join(self.tmp, "json")
        os.makedirs(json_dir)
        for number in (1, 2):
            with open(os.path.join(json_dir, f"{number:05}.json"), "w", encoding="utf-8") as fh:
                json.dump({"title": f"c{number}", "body": "<p>hello</p>"}, fh)
        subprocess.run(["7z", "a", "json.7z", "json"], cwd=self.tmp, check=True, capture_output=True)
        shutil.rmtree(json_dir)

        result = chapter_utils.read_chapters_no_extract(self.tmp, [1, 2])

        self.assertEqual(result, {1: {"title": "c1", "body": "<p>hello</p>"},
                                  2: {"title": "c2", "body": "<p>hello</p>"}})
        self.assertFalse(os.path.exists(json_dir))


def _words(prefix, chapter, count=300):
    return " ".join(f"{prefix}{chapter}w{i}" for i in range(count))


class Phase3Base(MergeTestCase):
    def _novel(self, slug, age_days=8):
        novel = Novel.objects.create(title=slug.title(), slug=slug, novel_path=slug)
        Novel.objects.filter(pk=novel.pk).update(
            created_at=timezone.now() - timedelta(days=age_days)
        )
        return novel

    def _text_source(self, novel, ext, folder, bodies, archived=False):
        """Source with real chapter files; ``archived`` leaves only json.7z."""
        source_path = os.path.join(folder, ext.source_name)
        abs_dir = os.path.join(self.tmp, source_path)
        json_dir = os.path.join(abs_dir, "json")
        os.makedirs(json_dir, exist_ok=True)
        source = NovelFromSource.objects.create(
            novel=novel,
            external_source=ext,
            title=novel.title,
            source_url=f"http://{ext.source_name}/{folder}",
            source_path=source_path,
            source_slug=ext.source_name,
            language="en",
            status="Ongoing",
            synopsis="",
        )
        for number, body in bodies.items():
            with open(os.path.join(json_dir, f"{number:05}.json"), "w", encoding="utf-8") as fh:
                json.dump({"title": f"Chapter {number}", "body": body}, fh)
            Chapter.objects.create(
                novel_from_source=source,
                chapter_id=number,
                url=f"{source.source_url}/ch{number}",
                title=f"Chapter {number}",
            )
        if archived:
            open(os.path.join(abs_dir, "json.7z"), "wb").close()
            shutil.rmtree(json_dir)
        return source

    def _phase3_command(self):
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
        cmd.root = self.tmp
        cmd.trash_root = os.path.join(self.tmp, ".prune_trash")
        cmd.examined = 0
        cmd.kept_phase3 = 0
        cmd.deleted = 0
        cmd.cursor = {}
        cmd.cursor_scope = "-|100"
        cmd.age_cutoff = timezone.now() - timedelta(days=7)
        cmd.stdout = StringIO()
        return cmd

    @staticmethod
    def _ext_names():
        return {
            ext.id: normalize_source_name(ext.source_name)
            for ext in ExternalSource.objects.all()
        }


class PhaseThreeSimilarityTests(Phase3Base):
    def _pair(self, slug, dead_bodies, keeper_bodies):
        novel = self._novel(slug)
        dead = self._text_source(
            novel, ExternalSource.objects.create(source_name=f"{slug}-dead"),
            "dead", dead_bodies,
        )
        keeper = self._text_source(
            novel, ExternalSource.objects.create(source_name=f"{slug}-live"),
            "live", keeper_bodies,
        )
        return dead, keeper

    def test_same_text_with_inserted_ad_and_punctuation_passes(self):
        dead_bodies = {n: _words("a", n) for n in (1, 2, 3)}
        keeper_bodies = {
            n: "support our team at example now! "
               + _words("a", n).replace("w1 ", "w1; ")
               + " thanks for reading!"
            for n in (1, 2, 3)
        }
        dead, keeper = self._pair("same", dead_bodies, keeper_bodies)

        cmd = self._phase3_command()
        mean, shift, count = cmd._content_similarity(cmd._dead_context(dead), keeper)

        self.assertGreaterEqual(mean, 0.90)
        self.assertEqual(shift, 0)
        self.assertGreater(count, 0)

    def test_unrelated_text_fails(self):
        dead_bodies = {n: _words("a", n) for n in (1, 2, 3)}
        keeper_bodies = {n: _words("z", n) for n in (1, 2, 3)}
        dead, keeper = self._pair("unrelated", dead_bodies, keeper_bodies)

        cmd = self._phase3_command()
        mean, _, _ = cmd._content_similarity(cmd._dead_context(dead), keeper)

        # No shared words at all: the mean stays at 0 and never passes.
        self.assertLess(mean, 0.90)


class PhaseThreeCandidateTests(Phase3Base):
    def test_dead_source_without_live_sibling_is_not_examined(self):
        lonely = self._novel("lonely")
        self._text_source(
            lonely, ExternalSource.objects.create(source_name="deadsite"),
            "lonely", {1: _words("l", 1)},
        )
        self._text_source(
            lonely, ExternalSource.objects.create(source_name="otherdead"),
            "lonely", {1: _words("m", 1)},
        )
        paired = self._novel("paired")
        dead = self._text_source(
            paired, ExternalSource.objects.create(source_name="deadsite2"),
            "paired", {1: _words("p", 1)},
        )
        self._text_source(
            paired, ExternalSource.objects.create(source_name="livesite"),
            "paired", {1: _words("q", 1)},
        )

        cmd = self._phase3_command()
        seen = []
        with patch.object(Command, "_load_handled_sources", return_value={"livesite"}), \
                patch.object(cmd, "_consider_dead_source",
                             side_effect=lambda d, h, e: seen.append(d.pk)):
            cmd._phase_dead_duplicates()

        self.assertEqual(seen, [dead.pk])


class VerdictFixture(Phase3Base):
    def setUp(self):
        super().setUp()
        novel = self._novel("verdict")
        self.dead = self._text_source(
            novel, ExternalSource.objects.create(source_name="deadsite"),
            "verdict", {1: _words("d", 1), 2: _words("d", 2)},
        )
        self.keeper = self._text_source(
            novel, ExternalSource.objects.create(source_name="livesite"),
            "verdict", {1: _words("k", 1), 2: _words("k", 2), 3: _words("k", 3)},
        )
        self.ext_names = self._ext_names()

    def _consider(self, cmd):
        cmd._consider_dead_source(self.dead, {"livesite"}, self.ext_names)


class VerdictCacheTests(VerdictFixture):
    def test_unchanged_verdict_is_not_reread(self):
        cmd = self._phase3_command()
        with patch.object(chapter_utils, "read_chapters_no_extract",
                          wraps=chapter_utils.read_chapters_no_extract) as spy:
            self._consider(cmd)
            first = spy.call_count
            self.assertGreater(first, 0)
            self.assertEqual(cmd.kept_phase3, 1)

            self._consider(cmd)
            self.assertEqual(spy.call_count, first)
            self.assertEqual(cmd.kept_phase3, 2)

    def test_keeper_chapter_count_change_forces_recompare(self):
        cmd = self._phase3_command()
        with patch.object(chapter_utils, "read_chapters_no_extract",
                          wraps=chapter_utils.read_chapters_no_extract) as spy:
            self._consider(cmd)
            first = spy.call_count
            Chapter.objects.create(
                novel_from_source=self.keeper, chapter_id=4,
                url=f"{self.keeper.source_url}/ch4", title="Chapter 4",
            )
            self._consider(cmd)
            self.assertGreater(spy.call_count, first)

    def test_recheck_ignores_stored_verdict(self):
        cmd = self._phase3_command()
        self._consider(cmd)
        cmd.recheck = True
        with patch.object(chapter_utils, "read_chapters_no_extract",
                          wraps=chapter_utils.read_chapters_no_extract) as spy:
            self._consider(cmd)
        self.assertGreater(spy.call_count, 0)

    def test_dry_run_does_not_write_verdict_file(self):
        out = StringIO()
        with patch.object(Command, "_load_handled_sources", return_value={"livesite"}):
            call_command("prune_library", stdout=out)

        self.assertIn("examined 1 dead source(s)", out.getvalue())
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".prune_trash", "prune_phase3_kept.json")))

    def test_apply_writes_verdict_file(self):
        cmd = self._phase3_command()
        cmd.apply = True
        self._consider(cmd)
        cmd._save_verdicts()

        with open(os.path.join(self.tmp, ".prune_trash", "prune_phase3_kept.json"), encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(saved, {str(self.dead.pk): cmd.verdicts[str(self.dead.pk)]})


class PhaseTwoRepairTests(Phase3Base):
    def _archived_source(self, slug, bodies):
        novel = self._novel(slug)
        source = self._text_source(
            novel, ExternalSource.objects.create(source_name=f"{slug}-site"),
            slug, bodies, archived=True,
        )
        source.chapters.update(has_content=False)
        return source

    def _members(self, numbers):
        return {
            f"json/{n:05}.json": json.dumps({"title": f"c{n}", "body": _words("r", n)}).encode("utf-8")
            for n in numbers
        }

    def test_dry_run_changes_nothing_and_creates_no_json_folder(self):
        source = self._archived_source("repair-dry", {1: _words("r", 1), 2: _words("r", 2)})
        fake_run, _ = _fake_7z_extract(self._members((1, 2)))

        cmd = self._phase3_command()
        with patch.object(chapter_utils, "read_chapters_no_extract",
                          wraps=chapter_utils.read_chapters_no_extract) as spy, \
                patch("subprocess.run", side_effect=fake_run):
            cmd._phase_empty_sources()

        self.assertEqual(spy.call_count, 1)
        self.assertEqual(source.chapters.filter(has_content=True).count(), 0)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, source.source_path, "json")))
        self.assertIn("content present on disk", cmd.stdout.getvalue())

    def test_apply_repairs_has_content_without_extracting(self):
        source = self._archived_source("repair-apply", {1: _words("r", 1), 2: _words("r", 2)})
        fake_run, _ = _fake_7z_extract(self._members((1, 2)))

        cmd = self._phase3_command()
        cmd.apply = True
        with patch.object(chapter_utils, "read_chapters_no_extract",
                          wraps=chapter_utils.read_chapters_no_extract) as spy, \
                patch("subprocess.run", side_effect=fake_run):
            cmd._phase_empty_sources()

        self.assertEqual(spy.call_count, 1)
        self.assertEqual(source.chapters.filter(has_content=True).count(), 2)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, source.source_path, "json")))
        self.assertTrue(NovelFromSource.objects.filter(pk=source.pk).exists())

    def test_unreadable_archive_keeps_source(self):
        source = self._archived_source("unreadable", {1: _words("r", 1)})
        failed = subprocess.CompletedProcess([], 2)

        cmd = self._phase3_command()
        cmd.apply = True
        with patch("subprocess.run", return_value=failed):
            cmd._phase_empty_sources()

        self.assertIn("unreadable", cmd.stdout.getvalue())
        self.assertTrue(NovelFromSource.objects.filter(pk=source.pk).exists())

    def test_zero_row_source_with_json_files_is_kept(self):
        novel = self._novel("zero-rows")
        source = self._text_source(
            novel, ExternalSource.objects.create(source_name="zerosite"), "zero-rows", {},
        )
        with open(os.path.join(self.tmp, source.source_path, "json", "00001.json"), "w", encoding="utf-8") as fh:
            json.dump({"title": "c1", "body": _words("z", 1)}, fh)

        cmd = self._phase3_command()
        cmd.apply = True
        cmd._phase_empty_sources()

        self.assertIn("chapter files on disk but no rows", cmd.stdout.getvalue())
        self.assertTrue(NovelFromSource.objects.filter(pk=source.pk).exists())


class PhaseThreeAlignmentTests(Phase3Base):
    def _keeper_pair(self, dead_bodies, keeper_bodies, slug):
        novel = self._novel(slug)
        dead = self._text_source(
            novel, ExternalSource.objects.create(source_name=f"{slug}-dead"), "dead", dead_bodies,
        )
        keeper = self._text_source(
            novel, ExternalSource.objects.create(source_name=f"{slug}-live"), "live", keeper_bodies,
        )
        return dead, keeper

    def test_per_sample_alignment_and_placeholder_still_passes(self):
        dead_bodies = {n: _words("c", n) for n in range(1, 6)}
        dead_bodies[6] = "Failed to download chapter body"
        # The keeper has an extra chapter after dead chapter 2, so samples before
        # it align at 0 and samples after it align at +1.
        keeper_bodies = {1: _words("c", 1), 2: _words("c", 2), 3: _words("x", 99),
                         4: _words("c", 3), 5: _words("c", 4), 6: _words("c", 5),
                         7: _words("c", 6)}
        dead, keeper = self._keeper_pair(dead_bodies, keeper_bodies, "align")

        cmd = self._phase3_command()
        mean, shift, count = cmd._content_similarity(cmd._dead_context(dead), keeper)

        self.assertEqual(count, 5)
        self.assertGreaterEqual(mean, 0.90)
        self.assertEqual(shift, 1)

    def test_one_matching_sample_out_of_six_fails(self):
        dead_bodies = {n: _words("c", n) for n in range(1, 7)}
        keeper_bodies = {1: _words("c", 1)}
        keeper_bodies.update({n: _words("x", n) for n in range(2, 7)})
        dead, keeper = self._keeper_pair(dead_bodies, keeper_bodies, "onlyone")

        cmd = self._phase3_command()
        mean, _, count = cmd._content_similarity(cmd._dead_context(dead), keeper)

        self.assertEqual(count, 6)
        self.assertLess(mean, 0.90)

    def test_single_chapter_dead_source_can_be_superseded(self):
        dead, keeper = self._keeper_pair(
            {1: _words("c", 1)}, {1: _words("c", 1), 2: _words("z", 2)}, "single",
        )
        cmd = self._phase3_command()
        ext_names = self._ext_names()

        cmd._consider_dead_source(dead, {normalize_source_name("single-live")}, ext_names)

        self.assertEqual(cmd.deleted, 1)
        self.assertIn("would delete source", cmd.stdout.getvalue())


class VerdictSignatureTests(VerdictFixture):
    def test_samples_change_invalidates_verdict(self):
        cmd = self._phase3_command()
        with patch.object(chapter_utils, "read_chapters_no_extract",
                          wraps=chapter_utils.read_chapters_no_extract) as spy:
            self._consider(cmd)
            first = spy.call_count
            cmd.samples = 1
            self._consider(cmd)
        self.assertGreater(spy.call_count, first)

    def test_max_shift_change_invalidates_verdict(self):
        cmd = self._phase3_command()
        with patch.object(chapter_utils, "read_chapters_no_extract",
                          wraps=chapter_utils.read_chapters_no_extract) as spy:
            self._consider(cmd)
            first = spy.call_count
            cmd.max_shift = 2
            self._consider(cmd)
        self.assertGreater(spy.call_count, first)


class CommentPortingTests(Phase3Base):
    def setUp(self):
        super().setUp()
        novel = self._novel("ports")
        self.dead = self._text_source(
            novel, ExternalSource.objects.create(source_name="deadsite"),
            "ports", {1: _words("d", 1), 2: _words("d", 2)},
        )
        self.keeper = self._text_source(
            novel, ExternalSource.objects.create(source_name="livesite"),
            "ports", {1: _words("k", 1), 2: _words("k", 2)},
        )
        # With shift=1 the last dead chapter has no keeper chapter to land on.
        last_dead = self.dead.chapters.order_by("chapter_id").last()
        self.comment = Comment.objects.create(chapter=last_dead, author_name="anon", message="hi")
        self.abs_dead = os.path.join(self.tmp, self.dead.source_path)

    def test_unmapped_comment_aborts_deletion_without_force(self):
        cmd = self._phase3_command()
        cmd.apply = True
        deleted = cmd._delete_source_named(self.dead, "test", keeper=self.keeper, shift=1)

        self.assertFalse(deleted)
        self.assertTrue(NovelFromSource.objects.filter(pk=self.dead.pk).exists())
        self.assertTrue(Comment.objects.filter(pk=self.comment.pk).exists())
        self.assertTrue(os.path.isdir(self.abs_dead))
        self.assertIn("KEEP source", cmd.stdout.getvalue())

    def test_unmapped_comment_dropped_and_audited_with_force(self):
        cmd = self._phase3_command()
        cmd.apply = True
        cmd.force = True
        deleted = cmd._delete_source_named(self.dead, "test", keeper=self.keeper, shift=1)

        self.assertTrue(deleted)
        self.assertFalse(Comment.objects.filter(pk=self.comment.pk).exists())
        with open(os.path.join(self.tmp, ".prune_trash", "audit.jsonl"), encoding="utf-8") as fh:
            entry = json.loads(fh.readline())
        self.assertEqual(entry["dropped_comments"], 1)

    def test_dry_run_reports_refusal_and_changes_nothing(self):
        cmd = self._phase3_command()
        deleted = cmd._delete_source_named(self.dead, "test", keeper=self.keeper, shift=1)

        self.assertFalse(deleted)
        self.assertIn("would KEEP source", cmd.stdout.getvalue())
        self.assertTrue(NovelFromSource.objects.filter(pk=self.dead.pk).exists())
        self.assertTrue(os.path.isdir(self.abs_dead))

    def test_folder_moves_only_after_successful_delete(self):
        cmd = self._phase3_command()
        cmd.apply = True
        rel = self.dead.source_path  # delete unlinks the folder from the row in memory
        self.assertTrue(cmd._delete_source_named(self.dead, "test"))

        self.assertFalse(os.path.isdir(self.abs_dead))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, ".prune_trash", rel)))

    def test_failed_delete_leaves_folder_in_place(self):
        cmd = self._phase3_command()
        cmd.apply = True
        with patch.object(NovelFromSource, "delete", side_effect=RuntimeError("boom")):
            deleted = cmd._delete_source_named(self.dead, "test")

        self.assertFalse(deleted)
        self.assertTrue(os.path.isdir(self.abs_dead))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".prune_trash")))


class VoteAndFallbackTests(Phase3Base):
    def _keeper_pair(self, dead_bodies, keeper_bodies, slug):
        novel = self._novel(slug)
        dead = self._text_source(
            novel, ExternalSource.objects.create(source_name=f"{slug}-dead"), "dead", dead_bodies,
        )
        keeper = self._text_source(
            novel, ExternalSource.objects.create(source_name=f"{slug}-live"), "live", keeper_bodies,
        )
        return dead, keeper

    def test_two_valid_of_six_samples_is_kept(self):
        dead_bodies = {1: _words("c", 1), 2: _words("c", 2)}
        dead_bodies.update({n: "Failed to download chapter body" for n in range(3, 7)})
        keeper_bodies = {n: _words("c", n) for n in range(1, 7)}
        dead, keeper = self._keeper_pair(dead_bodies, keeper_bodies, "twoof")

        cmd = self._phase3_command()
        _, _, count = cmd._content_similarity(cmd._dead_context(dead), keeper)

        self.assertEqual(count, 0)

    def test_shift_vote_ignores_non_matching_samples(self):
        dead_bodies = {n: _words("c", n) for n in range(1, 6)}
        # Samples 3-5 only partly match at +3, below the threshold: they must not
        # vote, or +3 would win 3 to 2.
        partial = lambda n: " ".join(f"c{n}w{i}" for i in range(100)) + " " + _words("y", n, 200)
        keeper_bodies = {
            1: _words("c", 1), 2: _words("c", 2),
            3: _words("x", 3), 4: _words("x", 4), 5: _words("x", 5),
            6: partial(3), 7: partial(4), 8: partial(5),
        }
        dead, keeper = self._keeper_pair(dead_bodies, keeper_bodies, "vote")

        cmd = self._phase3_command()
        cmd.threshold = 0.5
        mean, shift, count = cmd._content_similarity(cmd._dead_context(dead), keeper)

        self.assertEqual(count, 5)
        self.assertEqual(shift, 0)
        self.assertGreaterEqual(mean, 0.5)

    def test_no_majority_shift_is_kept(self):
        dead_bodies = {n: _words("c", n) for n in range(1, 5)}
        keeper_bodies = {1: _words("c", 1), 2: _words("c", 2), 3: _words("x", 3),
                         4: _words("c", 3), 5: _words("c", 4)}
        dead, keeper = self._keeper_pair(dead_bodies, keeper_bodies, "tie")

        cmd = self._phase3_command()
        mean, shift, count = cmd._content_similarity(cmd._dead_context(dead), keeper)

        # Two samples at 0 and two at +1: no strict majority, so no consistent alignment.
        self.assertEqual(count, 0)
        self.assertEqual(shift, 0)
        self.assertGreater(mean, 0.9)

    def test_second_keeper_tried_after_refused_comments(self):
        novel = self._novel("two-keepers")
        dead = self._text_source(
            novel, ExternalSource.objects.create(source_name="dead-x"), "tk-dead",
            {1: _words("c", 1), 2: _words("c", 2)},
        )
        keeper_a = self._text_source(
            novel, ExternalSource.objects.create(source_name="aaa-live"), "tk-a",
            {1: _words("a", 1), 2: _words("a", 2)},
        )
        keeper_b = self._text_source(
            novel, ExternalSource.objects.create(source_name="bbb-live"), "tk-b",
            {1: _words("c", 1), 2: _words("c", 2)},
        )
        Comment.objects.create(
            chapter=dead.chapters.order_by("chapter_id").last(),
            author_name="anon", message="hi",
        )

        def similarity(dead_ctx, keeper):
            # Keeper A aligns at +1, so the dead source's last comment has no target.
            if keeper.pk == keeper_a.pk:
                return 1.0, 1, 2
            return 1.0, 0, 2

        dead_id = dead.id  # Django clears pk on the instance once it is deleted
        cmd = self._phase3_command()
        cmd.apply = True
        with patch.object(cmd, "_find_keepers", return_value=[keeper_a, keeper_b]), \
                patch.object(cmd, "_content_similarity", side_effect=similarity):
            cmd._consider_dead_source(
                dead, {"aaa-live", "bbb-live"}, self._ext_names(),
            )

        self.assertIn(f"KEEP source {dead_id}", cmd.stdout.getvalue())
        self.assertFalse(NovelFromSource.objects.filter(pk=dead_id).exists())
        self.assertEqual(cmd.deleted, 1)

    def test_move_to_trash_refuses_paths_outside_library(self):
        outside = tempfile.mkdtemp(prefix="lncrawl-outside-")
        self.addCleanup(shutil.rmtree, outside, True)
        cmd = self._phase3_command()
        cmd.apply = True

        rel = os.path.relpath(outside, self.tmp)
        self.assertIsNone(cmd._move_to_trash(rel))
        self.assertIsNone(cmd._move_to_trash("../x"))
        self.assertIsNone(cmd._move_to_trash("."))
        self.assertTrue(os.path.isdir(outside))
