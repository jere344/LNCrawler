import json
import os
import re
import shutil
import tempfile
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.cache import cache
from django.db.models import Sum
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Chapter,
    ChatMessage,
    Comment,
    ExternalSource,
    FeaturedNovel,
    Job,
    LibraryFolder,
    Novel,
    NovelAlias,
    NovelBookmark,
    NovelFromSource,
    NovelRating,
    NovelSimilarity,
    ReadingHistory,
    ReadingList,
    ReadingListCollaborator,
    ReadingListItem,
    Review,
    SourceVote,
    Tag,
    TagAlias,
    WeeklySourceView,
)
from .services import (
    MergeError,
    SplitError,
    build_merge_plan,
    move_sources,
    merge_novels,
    merge_similar_tags,
    merge_tags,
    split_novel,
)
from .utils import resolve_novel_slug


def write_chapter(source_dir, number, body_size=3000):
    """Write a chapter JSON file big enough to count as real content."""
    json_dir = os.path.join(source_dir, "json")
    os.makedirs(json_dir, exist_ok=True)
    path = os.path.join(json_dir, f"{number:05}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {"title": f"Chapter {number}", "body": "word " * (body_size // 5)},
            handle,
        )
    return path


class MergeTestCase(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-merge-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.output = override_settings(LNCRAWL_OUTPUT_PATH=self.tmp)
        self.output.enable()
        self.addCleanup(self.output.disable)

    def make_source(
        self,
        novel,
        external_source,
        title,
        url,
        novel_folder,
        source_folder,
        chapters=0,
    ):
        source_path = os.path.join(novel_folder, source_folder)
        abs_dir = os.path.join(self.tmp, source_path)
        os.makedirs(abs_dir, exist_ok=True)
        for number in range(1, chapters + 1):
            write_chapter(abs_dir, number)
        source = NovelFromSource.objects.create(
            novel=novel,
            external_source=external_source,
            title=title,
            source_url=url,
            source_path=source_path,
            source_slug=source_folder,
            language="en",
            status="Ongoing",
            synopsis="",
        )
        for number in range(1, chapters + 1):
            Chapter.objects.create(
                novel_from_source=source,
                chapter_id=number,
                url=f"{url}/ch{number}",
                title=f"Chapter {number}",
            )
        return source


class MergeNovelsTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.target = Novel.objects.create(
            title="Lord of the Mysteries", slug="lotm", novel_path="lotm"
        )
        self.duplicate = Novel.objects.create(
            title="Lord of Mysteries", slug="lom", novel_path="lom"
        )
        self.es_a = ExternalSource.objects.create(source_name="novelfull")
        self.es_b = ExternalSource.objects.create(source_name="novelbin")

        self.target_source = self.make_source(
            self.target, self.es_a, "LOTM", "http://a/lotm", "lotm", "novelfull", 2
        )
        self.dup_source = self.make_source(
            self.duplicate, self.es_b, "lom", "http://b/lom", "lom", "novelbin", 3
        )
        self.dup_chapter = self.dup_source.chapters.first()

    def test_merge_combines_related_data_and_records_alias(self):
        user = get_user_model().objects.create_user(username="reader", password="x")

        NovelRating.objects.create(
            novel=self.duplicate, ip_address="1.1.1.1", rating=4
        )
        self.dup_source.total_views = 5
        self.dup_source.save(update_fields=["total_views"])
        WeeklySourceView.objects.create(
            source=self.dup_source,
            granularity=WeeklySourceView.DAY,
            day=date.today(),
            views=3,
        )
        FeaturedNovel.objects.create(novel=self.duplicate, description="featured")
        other = Novel.objects.create(title="Other", slug="other", novel_path="other")
        NovelSimilarity.objects.create(
            from_novel=self.duplicate, to_novel=other, similarity=0.9
        )

        Comment.objects.create(
            novel=self.duplicate, author_name="anon", message="novel comment"
        )
        Comment.objects.create(
            chapter=self.dup_chapter, author_name="anon", message="chapter comment"
        )

        Review.objects.create(
            novel=self.duplicate, user=user, title="Great", content="!", rating=5
        )
        NovelBookmark.objects.create(user=user, novel=self.duplicate)
        ReadingHistory.objects.create(
            user=user, novel=self.duplicate, source=self.dup_source
        )
        reading_list = ReadingList.objects.create(title="Faves", user=user)
        ReadingListItem.objects.create(reading_list=reading_list, novel=self.duplicate)
        SourceVote.objects.create(
            source=self.dup_source, ip_address="9.9.9.9", vote_type="up"
        )

        merge_novels(self.duplicate, self.target, move_files=True)

        self.assertFalse(Novel.objects.filter(slug="lom").exists())
        self.assertEqual(NovelAlias.objects.get(slug="lom").novel, self.target)

        self.dup_source.refresh_from_db()
        self.assertEqual(self.dup_source.novel, self.target)
        self.assertEqual(self.dup_source.title, "lom")
        self.assertEqual(self.dup_source.source_path, os.path.join("lotm", "novelbin"))

        self.assertEqual(self.target.ratings.count(), 1)
        # Views from the discarded duplicate source followed its story.
        self.assertEqual(
            sum(s.total_views for s in self.target.sources.all()), 5
        )
        self.assertEqual(
            WeeklySourceView.objects.filter(source__novel=self.target).aggregate(
                total=Sum("views")
            )["total"],
            3,
        )
        self.assertTrue(FeaturedNovel.objects.filter(novel=self.target).exists())
        self.assertEqual(
            NovelSimilarity.objects.get(similarity=0.9).from_novel, self.target
        )
        self.assertEqual(self.target.comment_count, 2)
        self.assertEqual(self.target.reviews.count(), 1)
        self.assertTrue(NovelBookmark.objects.filter(user=user, novel=self.target).exists())
        history = ReadingHistory.objects.get(user=user)
        self.assertEqual(history.novel, self.target)
        self.assertEqual(history.source, self.dup_source)
        self.assertTrue(
            ReadingListItem.objects.filter(reading_list=reading_list, novel=self.target).exists()
        )
        self.assertEqual(self.dup_source.votes.count(), 1)

        self.assertEqual(resolve_novel_slug("lom"), self.target)
        self.assertEqual(resolve_novel_slug("lotm"), self.target)

    def test_new_source_auto_joins_aliased_novel(self):
        merge_novels(self.duplicate, self.target, move_files=True)

        # A later crawl of the discarded name lands in its own folder again.
        new_dir = os.path.join(self.tmp, "lom", "newsite")
        os.makedirs(new_dir, exist_ok=True)
        write_chapter(new_dir, 1)
        meta_path = os.path.join(new_dir, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "novel": {
                        "title": "Lord Of Mysteries",
                        "url": "http://newsite/lom",
                        "chapters": [
                            {"id": 1, "url": "http://newsite/lom/1", "title": "Chapter 1"}
                        ],
                    }
                },
                handle,
            )

        source = NovelFromSource.from_meta_json(meta_path)

        self.assertEqual(source.novel, self.target)
        self.assertFalse(Novel.objects.filter(slug="lom").exists())
        self.assertEqual(source.source_path, os.path.join("lotm", "newsite"))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "lotm", "newsite")))

        # Re-importing the same source (an update) must keep it under the target.
        updated = NovelFromSource.from_meta_json(
            os.path.join(self.tmp, "lotm", "newsite", "meta.json")
        )
        self.assertEqual(updated.pk, source.pk)
        self.assertEqual(updated.novel, self.target)
        self.assertFalse(Novel.objects.filter(slug="lom").exists())

    def test_merge_rejects_same_novel(self):
        with self.assertRaises(MergeError):
            build_merge_plan(self.target, self.target)


class MergeDuplicateSourceTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.target = Novel.objects.create(
            title="Lord of the Mysteries", slug="lotm", novel_path="lotm"
        )
        self.duplicate = Novel.objects.create(
            title="Lord of Mysteries", slug="lom", novel_path="lom"
        )
        self.external = ExternalSource.objects.create(source_name="novelfull")

        # Existing target copy has fewer chapters than the incoming duplicate.
        self.winner = self.make_source(
            self.target, self.external, "LOTM", "http://a/lotm", "lotm", "novelfull", 2
        )
        self.loser = self.make_source(
            self.duplicate, self.external, "lom", "http://a/lom", "lom", "novelfull", 3
        )

    def test_same_external_source_is_collapsed_to_the_more_complete_copy(self):
        user = get_user_model().objects.create_user(username="reader", password="x")
        ReadingHistory.objects.create(
            user=user, novel=self.duplicate, source=self.loser
        )
        # Same voter on both copies, plus a voter only on the discarded copy.
        SourceVote.objects.create(
            source=self.loser, ip_address="1.1.1.1", vote_type="up"
        )
        SourceVote.objects.create(
            source=self.winner, ip_address="1.1.1.1", vote_type="down"
        )
        SourceVote.objects.create(
            source=self.loser, ip_address="8.8.8.8", vote_type="up"
        )

        merge_novels(self.duplicate, self.target, move_files=True)

        self.assertEqual(
            self.target.sources.filter(external_source=self.external).count(), 1
        )
        survivor = self.target.sources.get(external_source=self.external)
        self.assertEqual(survivor.title, "lom")
        self.assertEqual(survivor.chapters.count(), 3)

        # The discarded copy's history moved; its unique voter transferred while
        # the colliding one was dropped.
        self.assertEqual(ReadingHistory.objects.get(user=user).source, survivor)
        self.assertEqual(survivor.votes.count(), 2)
        self.assertFalse(SourceVote.objects.filter(source=self.winner).exists())


class MergeAdminTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.target = Novel.objects.create(
            title="Lord of the Mysteries", slug="lotm", novel_path="lotm"
        )
        self.duplicate = Novel.objects.create(
            title="Lord of Mysteries", slug="lom", novel_path="lom"
        )
        external = ExternalSource.objects.create(source_name="novelfull")
        self.make_source(
            self.duplicate, external, "lom", "http://a/lom", "lom", "novelfull", 1
        )
        self.admin = get_user_model().objects.create_superuser(
            username="admin", password="x"
        )
        self.client.force_login(self.admin)

    def test_admin_merge_page_previews_then_merges(self):
        url = reverse("admin:lncrawler_api_novel_merge")

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            url, {"source_novel": self.duplicate.pk, "target_novel": self.target.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Novel.objects.filter(slug="lom").exists())
        self.assertContains(response, "Confirm merge")

        response = self.client.post(
            url,
            {
                "source_novel": self.duplicate.pk,
                "target_novel": self.target.pk,
                "move_files": "on",
                "confirm": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Novel.objects.filter(slug="lom").exists())
        self.assertEqual(NovelAlias.objects.get(slug="lom").novel, self.target)


class SplitNovelTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.novel = Novel.objects.create(
            title="Re:Zero", slug="rezero", novel_path="rezero"
        )
        self.es_ln = ExternalSource.objects.create(source_name="lightnovel")
        self.es_web = ExternalSource.objects.create(source_name="webnovel")
        self.ln_source = self.make_source(
            self.novel,
            self.es_ln,
            "Re:Zero LN",
            "http://ln/rezero",
            "rezero",
            "lightnovel",
            3,
        )
        self.web_source = self.make_source(
            self.novel,
            self.es_web,
            "Re:Zero WN",
            "http://web/rezero",
            "rezero",
            "webnovel",
            2,
        )
        # A stale redirect that would otherwise steal the new slug on import.
        NovelAlias.objects.create(slug="rezero-webnovel", novel=self.novel)

    def write_meta(self, source, novel_url, chapter_count):
        source_dir = source.absolute_source_path
        with open(
            os.path.join(source_dir, "meta.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(
                {
                    "novel": {
                        "title": source.title,
                        "url": novel_url,
                        "chapters": [
                            {
                                "id": number,
                                "url": f"{novel_url}/ch{number}",
                                "title": f"Chapter {number}",
                            }
                            for number in range(1, chapter_count + 1)
                        ],
                    }
                },
                handle,
            )

    def test_split_creates_new_novel_and_survives_updates(self):
        user = get_user_model().objects.create_user(username="reader", password="x")
        NovelRating.objects.create(novel=self.novel, ip_address="1.1.1.1", rating=5)
        self.web_source.total_views = 7
        self.web_source.save(update_fields=["total_views"])
        Comment.objects.create(
            novel=self.novel, author_name="anon", message="novel comment"
        )
        Comment.objects.create(
            chapter=self.web_source.chapters.first(),
            author_name="anon",
            message="chapter comment",
        )
        ReadingHistory.objects.create(
            user=user, novel=self.novel, source=self.web_source
        )

        # File moves are queued with transaction.on_commit, which a TestCase's
        # wrapping transaction would otherwise swallow; run them explicitly.
        with self.captureOnCommitCallbacks(execute=True):
            new = split_novel(
                self.novel,
                [self.web_source],
                new_title="Re:Zero [Web Novel]",
                new_slug="rezero-webnovel",
                rename_title="Re:Zero [Light Novel]",
            )

        self.assertEqual(new.title, "Re:Zero [Web Novel]")
        self.assertEqual(new.slug, "rezero-webnovel")
        self.assertEqual(new.novel_path, "rezero-webnovel")

        self.novel.refresh_from_db()
        self.web_source.refresh_from_db()
        self.ln_source.refresh_from_db()

        self.assertEqual(self.novel.title, "Re:Zero [Light Novel]")
        self.assertEqual(self.web_source.novel, new)
        self.assertEqual(self.web_source.title, "Re:Zero WN")
        self.assertEqual(
            self.web_source.source_path, os.path.join("rezero-webnovel", "webnovel")
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.tmp, "rezero-webnovel", "webnovel", "json", "00001.json"
                )
            )
        )
        self.assertEqual(self.ln_source.novel, self.novel)

        # Novel-level data stays on the original novel.
        self.assertEqual(NovelRating.objects.get(ip_address="1.1.1.1").novel, self.novel)
        # Views travel with the source that was split off.
        self.assertEqual(new.sources.get(pk=self.web_source.pk).total_views, 7)
        self.assertEqual(Comment.objects.filter(novel=self.novel).count(), 1)
        self.assertEqual(self.novel.comment_count, 1)
        self.assertEqual(new.comment_count, 1)

        # Reading history follows the moved source.
        history = ReadingHistory.objects.get(user=user)
        self.assertEqual(history.novel, new)
        self.assertEqual(history.source, self.web_source)

        # The stale alias was cleared so the new slug is a real novel.
        self.assertFalse(NovelAlias.objects.filter(slug="rezero-webnovel").exists())

        # A future crawl under the new folder attaches to the split novel
        # without recreating it or downloading into the wrong folder.
        self.write_meta(self.web_source, "http://web/rezero", 2)
        updated = NovelFromSource.from_meta_json(
            os.path.join(self.tmp, "rezero-webnovel", "webnovel", "meta.json")
        )
        self.assertEqual(updated.pk, self.web_source.pk)
        self.assertEqual(updated.novel, new)
        self.assertEqual(Novel.objects.filter(slug="rezero-webnovel").count(), 1)
        self.assertEqual(
            updated.source_path, os.path.join("rezero-webnovel", "webnovel")
        )

    def test_move_sources_into_existing_novel_dedupes(self):
        target = Novel.objects.create(
            title="Re:Zero WN", slug="rezero-wn", novel_path="rezero-wn"
        )
        # The target already has a smaller copy of the same external source.
        existing = self.make_source(
            target,
            self.es_web,
            "old",
            "http://old/rezero",
            "rezero-wn",
            "webnovel",
            1,
        )
        user = get_user_model().objects.create_user(username="reader", password="x")
        ReadingHistory.objects.create(
            user=user, novel=self.novel, source=self.web_source
        )

        moved = move_sources(self.novel, [self.web_source], target)

        self.assertEqual(moved, target)
        self.assertEqual(target.sources.filter(external_source=self.es_web).count(), 1)
        survivor = target.sources.get(external_source=self.es_web)
        self.assertEqual(survivor.pk, self.web_source.pk)
        self.assertEqual(survivor.title, "Re:Zero WN")
        self.assertEqual(survivor.chapters.count(), 2)
        self.assertFalse(NovelFromSource.objects.filter(pk=existing.pk).exists())

        history = ReadingHistory.objects.get(user=user)
        self.assertEqual(history.novel, target)
        self.assertEqual(history.source, survivor)
        self.assertEqual(self.novel.sources.count(), 1)

    def test_split_requires_leaving_a_source(self):
        with self.assertRaises(SplitError):
            split_novel(
                self.novel,
                [self.ln_source, self.web_source],
                new_title="Everything",
                new_slug="everything",
            )

    def test_move_sources_into_existing_novel_without_duplicate(self):
        target = Novel.objects.create(
            title="Re:Zero House", slug="house", novel_path="house"
        )

        with self.captureOnCommitCallbacks(execute=True):
            move_sources(self.novel, [self.web_source], target)

        self.web_source.refresh_from_db()
        self.assertEqual(self.web_source.novel, target)
        self.assertEqual(
            self.web_source.source_path, os.path.join("house", "webnovel")
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(self.tmp, "house", "webnovel", "json", "00001.json")
            )
        )
        self.assertEqual(self.novel.sources.count(), 1)

    def test_split_slug_is_normalized_for_future_updates(self):
        with self.captureOnCommitCallbacks(execute=True):
            new = split_novel(
                self.novel,
                [self.web_source],
                new_title="Re:Zero WN",
                new_slug="ReZero_WN",
            )

        # The slug must be exactly what slugify() derives from the folder,
        # otherwise a future import would derive a different novel identity.
        self.assertEqual(new.slug, "rezero_wn")
        self.assertEqual(new.novel_path, "rezero_wn")

        self.write_meta(self.web_source, "http://web/rezero", 2)
        updated = NovelFromSource.from_meta_json(
            os.path.join(self.tmp, "rezero_wn", "webnovel", "meta.json")
        )
        self.assertEqual(updated.novel, new)
        self.assertEqual(Novel.objects.filter(slug="rezero_wn").count(), 1)

    def test_split_form_validates_selection_and_slug(self):
        from .admin.novel_admin import SplitNovelForm

        base = {"sources": [self.web_source.pk], "mode": "new", "new_title": "WN"}

        taken = Novel.objects.create(title="Taken", slug="taken", novel_path="taken")
        self.assertFalse(
            SplitNovelForm({**base, "new_slug": taken.slug}, novel=self.novel).is_valid()
        )
        self.assertFalse(
            SplitNovelForm(
                {**base, "new_slug": self.novel.slug}, novel=self.novel
            ).is_valid()
        )
        self.assertFalse(
            SplitNovelForm(
                {
                    "sources": [self.web_source.pk],
                    "mode": SplitNovelForm.MODE_EXISTING,
                    "target_novel": self.novel.pk,
                },
                novel=self.novel,
            ).is_valid()
        )


class SplitAdminTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.novel = Novel.objects.create(
            title="Re:Zero", slug="rezero", novel_path="rezero"
        )
        es_ln = ExternalSource.objects.create(source_name="lightnovel")
        es_web = ExternalSource.objects.create(source_name="webnovel")
        self.make_source(
            self.novel, es_ln, "LN", "http://ln/rezero", "rezero", "lightnovel", 1
        )
        self.web_source = self.make_source(
            self.novel, es_web, "WN", "http://web/rezero", "rezero", "webnovel", 1
        )
        self.admin = get_user_model().objects.create_superuser(
            username="admin", password="x"
        )
        self.client.force_login(self.admin)

    def test_admin_split_previews_then_creates_novel(self):
        url = reverse("admin:lncrawler_api_novel_split")

        self.assertEqual(self.client.get(url).status_code, 200)

        response = self.client.post(url, {"novel": self.novel.pk, "choose": "1"})
        self.assertEqual(response.status_code, 302)

        list_url = f"{url}?novel={self.novel.pk}"
        self.assertEqual(self.client.get(list_url).status_code, 200)

        payload = {
            "novel": self.novel.pk,
            "sources": [self.web_source.pk],
            "mode": "new",
            "new_title": "Re:Zero [Web Novel]",
            "new_slug": "rezero-webnovel",
            "rename_title": "Re:Zero [Light Novel]",
        }
        response = self.client.post(list_url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirm")
        self.assertFalse(Novel.objects.filter(slug="rezero-webnovel").exists())

        response = self.client.post(list_url, {**payload, "confirm": "1"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Novel.objects.filter(slug="rezero-webnovel").exists())

    def test_admin_split_moves_into_existing_novel(self):
        target = Novel.objects.create(
            title="Re:Zero House", slug="house", novel_path="house"
        )
        url = f"{reverse('admin:lncrawler_api_novel_split')}?novel={self.novel.pk}"
        payload = {
            "novel": self.novel.pk,
            "sources": [self.web_source.pk],
            "mode": "existing",
            "target_novel": target.pk,
        }

        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirm")
        self.assertEqual(self.novel.sources.count(), 2)

        response = self.client.post(url, {**payload, "confirm": "1"})
        self.assertEqual(response.status_code, 302)
        self.web_source.refresh_from_db()
        self.assertEqual(self.web_source.novel, target)
        self.assertEqual(self.novel.sources.count(), 1)


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
        from .management.commands.prune_library import Command

        user = get_user_model().objects.create_user(username="reader", password="x")
        comment = Comment.objects.create(
            chapter=self.dead_chapter, author_name="anon", message="hi"
        )
        ReadingHistory.objects.create(user=user, novel=self.novel, source=self.dead)
        SourceVote.objects.create(source=self.dead, ip_address="1.1.1.1", vote_type="up")
        # Same voter already voted on the keeper: the duplicate must be dropped.
        SourceVote.objects.create(
            source=self.keeper, ip_address="1.1.1.1", vote_type="down"
        )

        Command()._port_user_data(self.dead, self.keeper)

        comment.refresh_from_db()
        self.assertEqual(comment.chapter, self.keeper_chapter)
        self.assertEqual(ReadingHistory.objects.get(user=user).source, self.keeper)
        self.assertEqual(self.keeper.votes.count(), 1)
        self.keeper.refresh_from_db()
        self.assertEqual((self.keeper.upvotes, self.keeper.downvotes), (0, 1))
        self.novel.refresh_from_db()
        self.assertEqual(self.novel.comment_count, 1)

    def test_sample_percent_uses_md5_bucket_subset(self):
        import hashlib
        import uuid as uuidlib

        from .management.commands.prune_library import Command

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

        from .management.commands.prune_library import Command

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
        cmd.stdout = StringIO()

        cmd._phase_empty_sources()

        self.assertEqual(cmd.deleted, 0)
        self.assertTrue(NovelFromSource.objects.filter(pk=self.dead.pk).exists())
        self.assertIn("content present on disk", cmd.stdout.getvalue())
        self.assertFalse(self.dead.chapters.filter(has_content=False).exists())


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


class LanguageHelperTests(TestCase):
    def test_parse_languages_splits_dedupes_and_filters(self):
        from .languages import parse_languages

        self.assertEqual(
            parse_languages(["fr,en", "fr", "xx", "", None]), ["fr", "en"]
        )
        self.assertEqual(parse_languages(None), [])
        self.assertEqual(parse_languages("JA,ja"), ["ja"])


class LanguageAwareSourceTestCase(TestCase):
    """Shared fixtures: one novel with an English and a French source."""

    def setUp(self):
        cache.clear()
        self.novel = Novel.objects.create(title="Bilingue", slug="bilingue", novel_path="b")
        self.en_source = NovelFromSource.objects.create(
            novel=self.novel,
            external_source=ExternalSource.objects.create(source_name="en-site"),
            title="English",
            source_url="http://en/1",
            language="en",
            upvotes=0,
            downvotes=5,
        )
        self.fr_source = NovelFromSource.objects.create(
            novel=self.novel,
            external_source=ExternalSource.objects.create(source_name="fr-site"),
            title="Français",
            source_url="http://fr/1",
            language="fr",
            upvotes=3,
            downvotes=0,
        )

    def _source_titles(self, response):
        return [n["title"] for n in response.data["top_novels"]]


class HomeLanguageFilterTests(LanguageAwareSourceTestCase):
    def test_no_languages_param_returns_all_novels(self):
        response = self.client.get(reverse("home_page"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._source_titles(response), ["Bilingue"])

    def test_filtering_by_language_excludes_other_language_novels(self):
        other = Novel.objects.create(title="Only Japanese", slug="jp", novel_path="j")
        NovelFromSource.objects.create(
            novel=other,
            external_source=ExternalSource.objects.create(source_name="jp-site"),
            title="日本語",
            source_url="http://jp/1",
            language="ja",
        )

        response = self.client.get(reverse("home_page"), {"languages": "fr,en"})
        self.assertEqual(response.status_code, 200)
        titles = self._source_titles(response)
        self.assertIn("Bilingue", titles)
        self.assertNotIn("Only Japanese", titles)

    def test_multi_language_merges_novels_without_duplicates(self):
        # A novel whose source is available in both requested languages must
        # appear exactly once in the merged ranking.
        both = Novel.objects.create(title="Both", slug="both", novel_path="bo")
        for lang, name in (("fr", "fr2"), ("en", "en2")):
            NovelFromSource.objects.create(
                novel=both,
                external_source=ExternalSource.objects.create(source_name=name),
                title=name,
                source_url=f"http://{name}/1",
                language=lang,
            )

        response = self.client.get(reverse("home_page"), {"languages": ["fr", "en"]})
        titles = self._source_titles(response)
        self.assertEqual(titles.count("Both"), 1)
        self.assertEqual(titles.count("Bilingue"), 1)

    def test_language_filtered_prefered_source_matches_language(self):
        response = self.client.get(reverse("home_page"), {"languages": "fr"})
        novel = next(n for n in response.data["top_novels"] if n["title"] == "Bilingue")
        self.assertEqual(novel["prefered_source"]["title"], "Français")

    def test_prefered_source_falls_back_when_language_absent(self):
        # English source (worst votes) wins only because fr is excluded.
        response = self.client.get(reverse("home_page"), {"languages": "en"})
        novel = next(n for n in response.data["top_novels"] if n["title"] == "Bilingue")
        self.assertEqual(novel["prefered_source"]["title"], "English")

    def test_language_filter_scopes_view_counts_and_badges(self):
        NovelFromSource.objects.filter(pk=self.en_source.pk).update(total_views=100)
        NovelFromSource.objects.filter(pk=self.fr_source.pk).update(total_views=7)

        response = self.client.get(reverse("home_page"), {"languages": "fr"})
        novel = next(n for n in response.data["top_novels"] if n["title"] == "Bilingue")
        self.assertEqual(novel["total_views"], 7)
        self.assertEqual(novel["languages"], ["fr"])


class ReadingSourceSerializationTests(LanguageAwareSourceTestCase):
    def _novel(self, response):
        return next(n for n in response.data["top_novels"] if n["title"] == "Bilingue")

    def test_reading_source_exposes_history_source_full_metadata(self):
        # History is on the worst-voted (non-preferred) source: the card must
        # still receive that source's metadata so it matches the opened page.
        user = get_user_model().objects.create_user(username="reader", password="x")
        chapter = Chapter.objects.create(
            novel_from_source=self.en_source,
            chapter_id=1,
            url="http://en/1/1",
            title="Chapter 1",
        )
        ReadingHistory.objects.create(
            user=user, novel=self.novel, source=self.en_source, last_read_chapter=chapter
        )

        self.client.force_login(user)
        response = self.client.get(reverse("home_page"))
        self.assertEqual(response.status_code, 200)
        novel = self._novel(response)
        self.assertEqual(novel["prefered_source"]["title"], "Français")
        self.assertEqual(novel["reading_source"]["title"], "English")

    def test_reading_source_absent_for_anonymous(self):
        response = self.client.get(reverse("home_page"))
        self.assertIsNone(self._novel(response)["reading_source"])


class SerializerProfileTests(TestCase):
    """One serializer per model, several profiles: each profile must emit the
    same fields the old per-view classes did, and excluded fields (and their
    queries) must never run."""

    NOVEL_FIELDS = {
        "card": [
            "id", "title", "slug", "avg_rating", "rating_count", "total_views",
            "weekly_views", "prefered_source", "languages", "is_bookmarked",
            "comment_count", "reading_history", "reading_source", "is_dmca",
        ],
        "featured": [
            "id", "title", "slug", "avg_rating", "rating_count", "total_views",
            "weekly_views", "prefered_source", "languages", "is_bookmarked",
            "comment_count", "reading_history", "reading_source", "is_dmca",
        ],
        "detail": [
            "id", "title", "slug", "sources", "created_at", "updated_at",
            "avg_rating", "rating_count", "user_rating", "total_views",
            "weekly_views", "prefered_source", "is_bookmarked", "comment_count",
            "reading_history", "reading_source", "similar_novels",
            "reading_lists", "is_dmca",
        ],
        "library": [
            "id", "title", "slug", "avg_rating", "rating_count", "total_views",
            "weekly_views", "prefered_source", "languages", "is_bookmarked",
            "comment_count", "reading_history", "reading_source", "is_dmca",
            "bookmark_id", "note", "folder", "folder_name", "position",
            "user_rating",
        ],
    }

    SOURCE_FIELDS = {
        "card": [
            "id", "title", "source_slug", "novel_slug", "cover_min_url",
            "authors", "tags", "chapters_count", "last_chapter_update",
            "latest_available_chapter",
        ],
        "featured": [
            "id", "title", "source_slug", "novel_slug", "cover_min_url",
            "authors", "tags", "chapters_count", "last_chapter_update",
            "latest_available_chapter", "synopsis", "novel_id",
        ],
        "detail": [
            "id", "title", "source_url", "source_name", "source_slug", "authors",
            "tags", "language", "synopsis", "has_crawler", "cover_min_url",
            "chapters_count", "volumes_count", "volumes", "last_chapter_update",
            "upvotes", "downvotes", "vote_score", "user_vote", "novel_id",
            "novel_slug", "novel_title", "cover_url", "latest_available_chapter",
            "first_available_chapter", "reading_history", "overview_url",
            "novelupdates_url", "status", "editors", "translators",
            "alternative_titles", "original_publisher", "english_publisher",
        ],
    }

    def test_novel_profiles_match_legacy_field_sets(self):
        from .serializers import NovelSerializer

        for profile, expected in self.NOVEL_FIELDS.items():
            self.assertEqual(
                list(NovelSerializer(profile=profile).fields), expected, profile
            )

    def test_source_profiles_match_legacy_field_sets(self):
        from .serializers import NovelSourceSerializer

        for profile, expected in self.SOURCE_FIELDS.items():
            self.assertEqual(
                list(NovelSourceSerializer(profile=profile).fields), expected, profile
            )

    def test_other_serializer_profiles_match_expected_field_sets(self):
        """Every merged serializer exposes the same fields its split classes
        used to, through a named profile."""
        from .serializers import (
            ChapterSerializer,
            CommentSerializer,
            ReadingHistorySerializer,
            ReadingListSerializer,
            ReviewSerializer,
            UserSerializer,
        )

        base_comment = [
            "id", "author_name", "message", "contains_spoiler", "created_at",
            "upvotes", "downvotes", "vote_score", "user", "replies",
            "has_replies", "user_vote",
        ]
        cases = {
            ChapterSerializer: {
                "card": [
                    "id", "chapter_id", "title", "url", "volume", "volume_title",
                    "has_content",
                ],
                "content": [
                    "id", "chapter_id", "title", "novel_title", "novel_id",
                    "novel_slug", "source_id", "source_name", "source_slug", "body",
                    "prev_chapter", "next_chapter", "images_path",
                    "source_overview_image_url",
                ],
            },
            ReadingHistorySerializer: {
                "card": ["id", "last_read_chapter", "last_read_at"],
                "detail": [
                    "id", "novel_slug", "source_slug", "last_read_chapter",
                    "last_read_at", "next_chapter", "source_latest_chapter",
                ],
            },
            ReadingListSerializer: {
                "card": [
                    "id", "title", "description", "is_public", "user", "user_role",
                    "collaborators", "items_count", "created_at", "updated_at",
                    "first_item", "items_names",
                ],
                "detail": [
                    "id", "title", "description", "is_public", "user", "user_role",
                    "collaborators", "items", "created_at", "updated_at",
                ],
            },
            CommentSerializer: {
                "novel": base_comment + ["type", "edited"],
                "chapter": base_comment + [
                    "type", "chapter_title", "chapter_id", "source_name",
                    "source_slug", "edited",
                ],
                "profile": base_comment + [
                    "target_type", "target_title", "target_slug",
                    "target_novel_slug", "target_source_slug",
                    "target_chapter_number",
                ],
            },
            ReviewSerializer: {
                "card": [
                    "id", "novel_title", "novel_slug", "user", "title", "content",
                    "rating", "created_at",
                ],
                "detail": [
                    "id", "novel_title", "novel_slug", "user", "title", "content",
                    "rating", "created_at", "updated_at", "reaction_count",
                    "reactions", "current_user_reaction",
                ],
            },
            UserSerializer: {
                "me": [
                    "id", "username", "email", "profile_pic", "banner", "bio",
                    "social_links", "privacy_settings", "date_joined", "last_login",
                    "word_read", "chapters_read_count", "chapters_not_read_yet_count",
                    "preferred_ui_language", "preferred_languages",
                    "language_filter_enabled", "discoverable", "pinned_novels",
                ],
                "compact": ["id", "username", "profile_pic"],
                "public": [
                    "id", "username", "profile_pic", "banner", "bio", "date_joined",
                    "social_links", "friendship_status", "friend_count", "visibility",
                    "pinned_novels", "stats", "currently_reading", "top_genres",
                    "recent_reads",
                ],
            },
        }

        for serializer_class, profiles in cases.items():
            for profile, expected in profiles.items():
                self.assertEqual(
                    list(serializer_class(profile=profile).fields),
                    expected,
                    f"{serializer_class.__name__}:{profile}",
                )

    def test_unknown_profile_is_rejected(self):
        from .serializers import NovelSerializer

        with self.assertRaises(ValueError):
            NovelSerializer(profile="nope")

    def test_library_user_rating_reads_bookmark_without_query(self):
        """The library profile's ``user_rating`` is the pre-annotated owner
        rating on the attached bookmark; it must never hit the ratings table
        (one query per bookmark otherwise)."""
        from types import SimpleNamespace

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from .serializers import NovelSerializer

        novel = self._make_novel(1)
        novel.library_bookmark = SimpleNamespace(owner_rating=5)

        shown = NovelSerializer(
            novel, profile="library",
            context={"request": None, "show_ratings": True},
        )
        with CaptureQueriesContext(connection) as captured:
            self.assertEqual(shown.get_user_rating(novel), 5)
        self.assertEqual(len(captured), 0)

        hidden = NovelSerializer(
            novel, profile="library",
            context={"request": None, "show_ratings": False},
        )
        self.assertIsNone(hidden.get_user_rating(novel))

    def _make_novel(self, index):
        novel = Novel.objects.create(
            title=f"Novel {index}", slug=f"novel-{index}", novel_path=f"n{index}"
        )
        source = NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name=f"site-{index}"),
            title=f"Source {index}",
            source_url=f"http://site/{index}",
            source_slug=f"site-{index}",
            language="en",
            synopsis="A long synopsis",
        )
        NovelRating.objects.create(novel=novel, ip_address="1.1.1.1", rating=4)
        WeeklySourceView.objects.create(source=source, day=timezone.localdate(), views=3)
        return novel

    def _list_queries(self, queryset):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from .serializers import NovelSerializer

        with CaptureQueriesContext(connection) as captured:
            NovelSerializer(queryset, many=True, context={"request": None}).data
        return len(captured)

    def test_list_profile_query_count_is_flat(self):
        """Serializing 2 vs 4 novels must cost the same: any growth is an N+1."""
        from .utils.query_helpers import apply_novel_prefetches

        for index in range(4):
            self._make_novel(index)
        queryset = apply_novel_prefetches(Novel.objects.all().order_by("title"), None)
        self.assertEqual(
            self._list_queries(queryset[:2]),
            self._list_queries(queryset[:4]),
        )

    def test_card_profile_serializes_without_extra_queries(self):
        """With the card fields annotated, serializing a source card must not
        touch the chapter/volume tables (the old detail-only fallbacks)."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from .serializers import NovelSourceSerializer
        from .utils.query_helpers import sources_queryset

        self._make_novel(1)
        source = sources_queryset(detailed=False).first()
        with CaptureQueriesContext(connection) as captured:
            NovelSourceSerializer(source, profile="card").data
        self.assertEqual(len(captured), 0)

    def test_novel_detail_endpoint_serializes_nested_sources(self):
        novel = self._make_novel(1)
        response = self.client.get(
            reverse("novel_detail_by_slug", kwargs={"novel_slug": novel.slug})
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["sources"]), 1)

    def test_source_detail_endpoint_serves_full_detail_profile(self):
        self._make_novel(1)
        response = self.client.get(
            reverse("source_detail", kwargs={"novel_slug": "novel-1", "source_slug": "site-1"})
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["synopsis"], "A long synopsis")
        self.assertIn("first_available_chapter", response.data)


class SearchLanguageFilterTests(LanguageAwareSourceTestCase):
    def test_legacy_single_language_param_still_works(self):
        response = self.client.get(reverse("search_novels"), {"language": "fr"})
        self.assertEqual(response.status_code, 200)
        titles = [n["title"] for n in response.data["results"]]
        self.assertEqual(titles, ["Bilingue"])

    def test_multi_language_param_merges_without_duplicates(self):
        response = self.client.get(
            reverse("search_novels"), {"languages": ["fr", "en"]}
        )
        self.assertEqual(response.status_code, 200)
        titles = [n["title"] for n in response.data["results"]]
        self.assertEqual(titles.count("Bilingue"), 1)


class TagAutocompleteAliasTests(TestCase):
    """A merged-away tag name must still surface its canonical tag."""

    def setUp(self):
        self.novel = Novel.objects.create(title="Isekai Tale", slug="it", novel_path="it")
        self.canonical = Tag.objects.create(name="Isekai")
        source = NovelFromSource.objects.create(
            novel=self.novel,
            external_source=ExternalSource.objects.create(source_name="tag-site"),
            title="Isekai Tale",
            source_url="http://tag/1",
        )
        source.tags.add(self.canonical)
        TagAlias.objects.create(name="isekai", tag=self.canonical)

    def _suggest(self, query):
        response = self.client.get(
            reverse("autocomplete_suggestion"), {"type": "tag", "query": query}
        )
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_alias_query_returns_canonical_tag(self):
        suggestions = self._suggest("isekai")
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["name"], "Isekai")
        self.assertEqual(suggestions[0]["alias"], "isekai")
        self.assertEqual(suggestions[0]["count"], 1)

    def test_canonical_and_alias_merge_into_one_entry(self):
        # "Isekai" (canonical) and "isekai" (alias) both match case-insensitively.
        self.assertEqual(len(self._suggest("sekai")), 1)


class TagSimilarityTests(TestCase):
    """The auto-merge heuristic must catch obvious variants, not real tags."""

    def _sim(self, a, b):
        from .services.merge_service import _tag_similarity

        return _tag_similarity(a, b)

    def test_case_only_difference_is_similar(self):
        self.assertGreaterEqual(self._sim("Isekai", "isekai"), 0.9)

    def test_plural_and_singular_are_similar(self):
        self.assertGreaterEqual(self._sim("action", "actions"), 0.9)

    def test_distinct_tags_are_not_similar(self):
        self.assertLess(self._sim("action", "romance"), 0.9)
        self.assertLess(self._sim("Isekai", "Isekaijoucho"), 0.9)

    def test_shared_prefix_words_are_not_similar(self):
        # Near but distinct sub-genres must survive.
        self.assertLess(self._sim("Science Fiction", "Science Fantasy"), 0.9)

    def test_direction_swapped_words_are_not_similar(self):
        # The classic false positives: one word changed, opposite meaning.
        self.assertLess(self._sim("Western Fantasy", "Eastern Fantasy"), 0.9)
        self.assertLess(self._sim("Female Protagonist", "Male Protagonist"), 0.9)
        self.assertLess(self._sim("Adapted to Manhua", "Adapted to Manhwa"), 0.9)

    def test_accents_fold(self):
        self.assertGreaterEqual(self._sim("Réincarnation", "reincarnation"), 0.9)


class MergeSimilarTagsTests(TestCase):
    def setUp(self):
        self.novel = Novel.objects.create(title="N", slug="n", novel_path="n")
        self.source = NovelFromSource.objects.create(
            novel=self.novel,
            external_source=ExternalSource.objects.create(source_name="s"),
            title="N",
            source_url="http://s/1",
        )

    def _tag(self, name, count=0):
        tag = Tag.objects.create(name=name)
        for _ in range(count):
            self.source.tags.add(tag)
        return tag

    def test_auto_merge_keeps_most_used_spelling(self):
        # "isekai" carries the data, so it wins over the uppercase spare.
        canonical = self._tag("isekai", count=1)
        self._tag("Isekai")

        results = merge_similar_tags()

        self.assertEqual(len(results), 1)
        self.assertEqual(Tag.objects.get(name="isekai"), canonical)
        self.assertFalse(Tag.objects.filter(name="Isekai").exists())
        self.assertEqual(TagAlias.objects.get(name="Isekai").tag, canonical)
        self.assertEqual(self.source.tags.count(), 1)

    def test_distinct_tags_are_left_alone(self):
        self._tag("Action")
        self._tag("Romance")
        self.assertEqual(merge_similar_tags(), [])
        self.assertEqual(Tag.objects.count(), 2)

    def test_dry_run_changes_nothing(self):
        self._tag("action", count=1)
        self._tag("actions")

        results = merge_similar_tags(dry_run=True)

        self.assertEqual(results, [("action", ["actions"])])
        self.assertEqual(Tag.objects.count(), 2)

    def test_aliased_name_resolves_on_reimport(self):
        # After auto-merge, importing the old spelling must not recreate it.
        self._tag("Isekai", count=1)
        self._tag("isekai")
        merge_similar_tags()

        self.assertEqual(Tag.resolve("isekai"), Tag.objects.get(name="Isekai"))
        self.assertFalse(Tag.objects.filter(name="isekai").exists())




class ProjectionInvariantTests(TestCase):
    def test_total_views_projection_matches_summed_buckets(self):
        novel = Novel.objects.create(title="Proj", slug="proj", novel_path="p")
        source = NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name="p-site"),
            title="Proj",
            source_url="http://p/1",
            language="en",
        )
        for _ in range(4):
            WeeklySourceView.increment_for_source(source)

        source.refresh_from_db()
        bucket_total = WeeklySourceView.objects.filter(source=source).aggregate(
            total=Sum("views")
        )["total"]
        self.assertEqual(source.total_views, 4)
        self.assertEqual(bucket_total, 4)

        # Rebuild the projection from the events and confirm it agrees.
        rebuilt = WeeklySourceView.objects.filter(source=source).aggregate(
            total=Sum("views")
        )["total"]
        NovelFromSource.objects.filter(pk=source.pk).update(total_views=rebuilt)
        source.refresh_from_db()
        self.assertEqual(source.total_views, 4)


class UserLanguagePreferenceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="lang", email="lang@example.com", password="pw12345!"
        )
        self.client.force_login(self.user)

    def test_defaults_and_round_trip(self):
        response = self.client.get(reverse("user_profile"))
        self.assertEqual(response.data["preferred_ui_language"], "")
        self.assertEqual(response.data["preferred_languages"], [])
        self.assertTrue(response.data["language_filter_enabled"])

        response = self.client.patch(
            reverse("user_profile"),
            data=json.dumps(
                {
                    "preferred_ui_language": "FR",
                    "preferred_languages": ["fr", "en", "xx", "fr"],
                    "language_filter_enabled": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_ui_language, "fr")
        self.assertEqual(self.user.preferred_languages, ["fr", "en"])
        self.assertFalse(self.user.language_filter_enabled)

    def test_invalid_language_rejected(self):
        response = self.client.patch(
            reverse("user_profile"),
            data=json.dumps({"preferred_languages": ["xx"]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.patch(
            reverse("user_profile"),
            data=json.dumps({"preferred_ui_language": "xx"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_clearing_languages_is_allowed(self):
        self.user.preferred_languages = ["fr"]
        self.user.save()

        response = self.client.patch(
            reverse("user_profile"),
            data=json.dumps({"preferred_languages": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_languages, [])

    def test_non_list_languages_rejected_not_500(self):
        response = self.client.patch(
            reverse("user_profile"),
            data=json.dumps({"preferred_languages": 123}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class RecommendationDedupTests(TestCase):
    def test_recommendation_ids_are_unique(self):
        user = get_user_model().objects.create_user(
            username="rec", email="rec@example.com", password="pw12345!"
        )
        target = Novel.objects.create(title="Target", slug="target", novel_path="t")
        for i in range(3):
            source = Novel.objects.create(
                title=f"Book {i}", slug=f"book-{i}", novel_path=f"b{i}"
            )
            NovelBookmark.objects.create(user=user, novel=source)
            NovelSimilarity.objects.create(
                from_novel=source, to_novel=target, similarity=0.1 * (i + 1)
            )

        self.client.force_login(user)
        response = self.client.get(reverse("list_bookmarked_novels"))
        self.assertEqual(response.status_code, 200)
        ids = [n["id"] for n in response.data["recommendations"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn(str(target.id), ids)


class PaginationRobustnessTests(TestCase):
    def test_bad_page_param_returns_first_page(self):
        Novel.objects.create(title="Only", slug="only", novel_path="o")
        for name in ("list_novels", "search_novels", "list_all_reading_lists"):
            response = self.client.get(reverse(name), {"page": "abc"})
            self.assertEqual(response.status_code, 200, name)
            self.assertEqual(response.data["current_page"], 1, name)


class ReadingListVisibilityTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="owner", email="owner@example.com", password="pw12345!")
        self.editor = get_user_model().objects.create_user(username="editor", email="editor@example.com", password="pw12345!")
        self.reader = get_user_model().objects.create_user(username="reader", email="reader@example.com", password="pw12345!")
        self.stranger = get_user_model().objects.create_user(username="stranger", email="stranger@example.com", password="pw12345!")

        self.novel = Novel.objects.create(title="Story", slug="story", novel_path="story")
        self.private = ReadingList.objects.create(title="Private", user=self.owner, is_public=False)
        self.public = ReadingList.objects.create(title="Public", user=self.owner, is_public=True)

        ReadingListCollaborator.objects.create(
            reading_list=self.private, user=self.editor, role=ReadingListCollaborator.EDITOR)
        ReadingListCollaborator.objects.create(
            reading_list=self.private, user=self.reader, role=ReadingListCollaborator.READER)

    def detail_url(self, reading_list):
        return reverse("reading_list_detail", kwargs={"list_id": reading_list.id})

    def test_browse_only_shows_public_lists(self):
        response = self.client.get(reverse("list_all_reading_lists"))
        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.data["results"]]
        self.assertIn("Public", titles)
        self.assertNotIn("Private", titles)

    def test_anonymous_cannot_read_private(self):
        self.assertEqual(self.client.get(self.detail_url(self.private)).status_code, 403)

    def test_anonymous_can_read_public(self):
        self.assertEqual(self.client.get(self.detail_url(self.public)).status_code, 200)

    def test_reader_can_read_private(self):
        self.client.force_login(self.reader)
        response = self.client.get(self.detail_url(self.private))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user_role"], "reader")

    def test_reader_cannot_add_item(self):
        self.client.force_login(self.reader)
        response = self.client.post(
            reverse("add_novel_to_list", kwargs={"list_id": self.private.id}),
            {"novel_id": str(self.novel.id)},
        )
        self.assertEqual(response.status_code, 403)

    def test_editor_can_add_item_but_not_delete_or_toggle(self):
        self.client.force_login(self.editor)
        add = self.client.post(
            reverse("add_novel_to_list", kwargs={"list_id": self.private.id}),
            {"novel_id": str(self.novel.id)},
        )
        self.assertEqual(add.status_code, 201, add.data)

        delete = self.client.delete(reverse("delete_reading_list", kwargs={"list_id": self.private.id}))
        self.assertEqual(delete.status_code, 403)

        toggle = self.client.put(
            reverse("update_reading_list", kwargs={"list_id": self.private.id}),
            data=json.dumps({"is_public": True}),
            content_type="application/json",
        )
        self.assertEqual(toggle.status_code, 403)

    def test_owner_can_toggle_visibility(self):
        self.client.force_login(self.owner)
        response = self.client.put(
            reverse("update_reading_list", kwargs={"list_id": self.private.id}),
            data=json.dumps({"is_public": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.private.refresh_from_db()
        self.assertTrue(self.private.is_public)

    def test_stranger_cannot_read_private(self):
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(self.detail_url(self.private)).status_code, 403)

    def test_user_lists_include_owned_and_shared(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("get_user_reading_lists"))
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(str(self.private.id), ids)

    def test_novel_detail_hides_private_list_from_anonymous(self):
        ReadingListItem.objects.create(reading_list=self.private, novel=self.novel)
        ReadingListItem.objects.create(reading_list=self.public, novel=self.novel)
        response = self.client.get(
            reverse("novel_detail_by_slug", kwargs={"novel_slug": self.novel.slug})
        )
        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.data["reading_lists"]]
        self.assertIn("Public", titles)
        self.assertNotIn("Private", titles)

    def test_novel_detail_shows_private_list_to_owner(self):
        ReadingListItem.objects.create(reading_list=self.private, novel=self.novel)
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse("novel_detail_by_slug", kwargs={"novel_slug": self.novel.slug})
        )
        titles = [item["title"] for item in response.data["reading_lists"]]
        self.assertIn("Private", titles)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ForgotPasswordEmailTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="resetuser", email="reset@example.com", password="pw12345!"
        )

    def test_forgot_password_sends_reset_link(self):
        from django.core import mail

        from auth_app.models import PasswordResetToken

        response = self.client.post(
            reverse("forgot_password"),
            data=json.dumps({"email": self.user.email}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.user.email])

        token = PasswordResetToken.objects.get(user=self.user)
        # Only the hash is stored; the email carries the raw token, so verify
        # the emailed link hashes back to the stored row.
        raw = re.search(r"token=([\w\-]+)", message.body).group(1)
        self.assertEqual(PasswordResetToken.hash_token(raw), token.token)
        html = next(content for content, mime in message.alternatives if mime == "text/html")
        self.assertIn(raw, html)


class LibraryReworkTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="libowner", email="libowner@example.com", password="pw12345!"
        )
        self.viewer = get_user_model().objects.create_user(
            username="libviewer", email="libviewer@example.com", password="pw12345!"
        )
        self.first = Novel.objects.create(title="Alpha", slug="alpha", novel_path="alpha")
        self.second = Novel.objects.create(title="Beta", slug="beta", novel_path="beta")
        self.owner.privacy_settings = {
            "library": "public",
            "library_notes": "public",
            "library_ratings": "public",
        }
        self.owner.save()

    def _bookmark(self, novel):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("add_novel_bookmark", kwargs={"novel_slug": novel.slug})
        )
        return str(response.data["bookmark_id"])

    def test_custom_reorder_persists(self):
        first_id = self._bookmark(self.first)
        second_id = self._bookmark(self.second)

        response = self.client.post(
            reverse("reorder_library"),
            data=json.dumps(
                [
                    {"id": second_id, "position": 0},
                    {"id": first_id, "position": 1},
                ]
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        listed = self.client.get(reverse("list_bookmarked_novels"))
        titles = [item["title"] for item in listed.data["results"]]
        self.assertEqual(titles, ["Beta", "Alpha"])

    def test_folder_assignment_and_filter(self):
        self.client.force_login(self.owner)
        created = self.client.post(
            reverse("library_folders"),
            data=json.dumps({"name": "Favorites"}),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        folder_id = created.data["id"]

        bookmark_id = self._bookmark(self.first)
        assigned = self.client.patch(
            reverse("update_library_item", kwargs={"bookmark_id": bookmark_id}),
            data=json.dumps({"folder": folder_id, "note": "great read"}),
            content_type="application/json",
        )
        self.assertEqual(assigned.status_code, 200, assigned.data)

        filtered = self.client.get(reverse("list_bookmarked_novels"), {"folder": folder_id})
        self.assertEqual([item["title"] for item in filtered.data["results"]], ["Alpha"])
        self.assertEqual(filtered.data["results"][0]["note"], "great read")
        self.assertEqual(filtered.data["folders"][0]["count"], 1)

    def test_public_mirror_shows_owner_rating_not_viewer(self):
        self._bookmark(self.first)
        self.client.post(
            reverse("rate_novel", kwargs={"novel_slug": self.first.slug}),
            data=json.dumps({"rating": 4}),
            content_type="application/json",
        )
        NovelRating.objects.create(novel=self.first, user=self.viewer, rating=5)
        NovelRating.objects.create(novel=self.first, ip_address="9.9.9.9", rating=1)

        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse("user_library", kwargs={"username": self.owner.username})
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["results"][0]["user_rating"], 4)

    def test_public_mirror_hides_rating_when_private(self):
        self._bookmark(self.first)
        self.client.post(
            reverse("rate_novel", kwargs={"novel_slug": self.first.slug}),
            data=json.dumps({"rating": 4}),
            content_type="application/json",
        )
        self.owner.privacy_settings = {
            **self.owner.privacy_settings,
            "library_ratings": "private",
        }
        self.owner.save()

        self.client.force_login(self.viewer)
        response = self.client.get(
            reverse("user_library", kwargs={"username": self.owner.username})
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["results"][0]["user_rating"])


class DedupHelperTests(TestCase):
    """Guards the shared helpers extracted from duplicated view/serializer code."""

    def test_friend_user_queryset_returns_accepted_either_direction(self):
        from .models.users_models import Friendship
        from .views.friends_views import friend_user_queryset

        User = get_user_model()
        alice = User.objects.create_user(username="alice", email="alice@x.com", password="x")
        bob = User.objects.create_user(username="bob", email="bob@x.com", password="x")
        carol = User.objects.create_user(username="carol", email="carol@x.com", password="x")
        Friendship.objects.create(requester=alice, addressee=bob, status=Friendship.ACCEPTED)
        Friendship.objects.create(requester=carol, addressee=alice, status=Friendship.PENDING)

        self.assertEqual(set(friend_user_queryset(alice)), {bob})
        self.assertEqual(set(friend_user_queryset(bob)), {alice})

    def test_build_media_url_encodes_and_prefixes(self):
        from .utils import build_media_url

        self.assertIsNone(build_media_url(None))
        self.assertTrue(build_media_url("a b/cover.jpg").endswith("/a%20b/cover.jpg"))


class NovelUpdatesImportTests(TestCase):
    """Read-only import of a NovelUpdates XML reading-list export."""

    SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<nu_readinglist>
<list>Reading (Manual)<series><title>D-Genesis</title><chp>v0c0</chp></series>
<series><title>Overgeared</title><chp>v0c1</chp></series>
<series><title>Kumo Desu ga, Nani ka?</title><chp>c823</chp></series>
<series><title>Untracked Thing</title><chp/></series>
</list>
<list>Completed<series><title>D-Genesis</title><chp/></series></list>
</nu_readinglist>"""

    def setUp(self):
        from .models import Volume

        self.user = get_user_model().objects.create_user(
            username="importer", email="importer@example.com", password="pw12345!"
        )
        self.novel = Novel.objects.create(
            title="D-Genesis", slug="d-genesis", novel_path="d-genesis"
        )
        self.source = NovelFromSource.objects.create(
            novel=self.novel,
            external_source=ExternalSource.objects.create(source_name="Test"),
            title="D-Genesis",
            source_url="http://src/dgenesis",
            source_slug="d-genesis",
            language="en",
            status="Ongoing",
            synopsis="",
        )
        for number in (1, 823):
            Chapter.objects.create(
                novel_from_source=self.source,
                chapter_id=number,
                url=f"http://src/dgenesis/{number}",
                title=f"Chapter {number}",
            )
        Volume.objects.create(
            novel_from_source=self.source, volume_id=1, title="Vol 1", start_chapter=1
        )

    def test_parse_chp_forms(self):
        from .services.novelupdates_import_service import parse_chp

        self.assertEqual(parse_chp("v0c0"), (0, 0))
        self.assertEqual(parse_chp("v0c1"), (0, 1))
        self.assertEqual(parse_chp("c823"), (0, 823))
        self.assertEqual(parse_chp("57"), (0, 57))
        self.assertEqual(parse_chp("v2c5"), (2, 5))
        self.assertEqual(parse_chp(""), (0, 0))
        self.assertEqual(parse_chp(None), (0, 0))

    def test_folder_name_strips_manual_suffix(self):
        from .services.novelupdates_import_service import folder_name_for

        self.assertEqual(folder_name_for("Reading (Manual)"), "Reading")
        self.assertEqual(folder_name_for("Completed"), "Completed")

    def test_parse_reads_lists_titles_and_progress(self):
        from .services.novelupdates_import_service import parse_nu_export

        entries = parse_nu_export(self.SAMPLE.encode("utf-8"))
        self.assertEqual(len(entries), 5)
        self.assertEqual(entries[0]["list_name"], "Reading (Manual)")
        self.assertEqual(entries[0]["title"], "D-Genesis")
        self.assertEqual(entries[2]["chapter"], 823)
        self.assertEqual(entries[3]["chapter"], 0)
        self.assertEqual(entries[4]["list_name"], "Completed")

    def test_parse_rejects_foreign_xml(self):
        from .services.novelupdates_import_service import parse_nu_export

        with self.assertRaises(ValueError):
            parse_nu_export(b"<foo><bar/></foo>")

    def test_parse_endpoint_matches_by_title(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("parse_novelupdates_import"),
            data={
                "file": SimpleUploadedFile(
                    "nu.xml", self.SAMPLE.encode("utf-8"), content_type="application/xml"
                )
            },
        )
        self.assertEqual(response.status_code, 200, response.data)
        first = response.data["entries"][0]
        self.assertEqual(first["title"], "D-Genesis")
        self.assertEqual(first["status"], "matched")
        self.assertEqual(first["folder"], "Reading")
        entries = {entry["title"]: entry for entry in response.data["entries"]}
        self.assertEqual(entries["Untracked Thing"]["status"], "unmatched")

    def _apply(self, entries):
        self.client.force_login(self.user)
        return self.client.post(
            reverse("apply_novelupdates_import"),
            data=json.dumps({"entries": entries}),
            content_type="application/json",
        )

    def test_apply_creates_bookmark_folder_and_progress(self):
        response = self._apply(
            [
                {
                    "novel_id": str(self.novel.id),
                    "folder": "Reading",
                    "volume": 0,
                    "chapter": 823,
                }
            ]
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["bookmarked"], 1)
        self.assertEqual(response.data["folders_created"], 1)
        self.assertEqual(response.data["progress_set"], 1)

        bookmark = NovelBookmark.objects.get(user=self.user, novel=self.novel)
        self.assertEqual(bookmark.folder.name, "Reading")
        history = ReadingHistory.objects.get(user=self.user, novel=self.novel)
        self.assertEqual(history.last_read_chapter.chapter_id, 823)

        again = self._apply([{"novel_id": str(self.novel.id), "chapter": 823}])
        self.assertEqual(again.data["already_bookmarked"], 1)
        self.assertEqual(again.data["bookmarked"], 0)

    def test_apply_volume_fallback_uses_start_chapter(self):
        response = self._apply(
            [{"novel_id": str(self.novel.id), "volume": 1, "chapter": 0}]
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["progress_set"], 1)
        history = ReadingHistory.objects.get(user=self.user, novel=self.novel)
        self.assertEqual(history.last_read_chapter.chapter_id, 1)

    def test_apply_requires_authentication(self):
        response = self.client.post(
            reverse("apply_novelupdates_import"),
            data=json.dumps({"entries": []}),
            content_type="application/json",
        )
        self.assertIn(response.status_code, (401, 403))

    def test_parse_requires_authentication(self):
        response = self.client.post(reverse("parse_novelupdates_import"))
        self.assertIn(response.status_code, (401, 403))

    def test_apply_ignores_non_dict_entries(self):
        response = self._apply(
            [1, "x", None, {"novel_id": str(self.novel.id), "chapter": 1}]
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["bookmarked"], 1)
        self.assertEqual(response.data["skipped"], 3)

    def test_apply_does_not_regress_progress(self):
        ReadingHistory.objects.create(
            user=self.user,
            novel=self.novel,
            source=self.source,
            last_read_chapter=Chapter.objects.get(
                novel_from_source=self.source, chapter_id=823
            ),
        )
        response = self._apply([{"novel_id": str(self.novel.id), "chapter": 1}])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["progress_set"], 0)
        history = ReadingHistory.objects.get(user=self.user, novel=self.novel)
        self.assertEqual(history.last_read_chapter.chapter_id, 823)

    def test_parse_ambiguous_when_titles_collide(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        Novel.objects.create(title="D-Genesis", slug="d-genesis-2", novel_path="d-genesis-2")
        self.client.force_login(self.user)
        sample = (
            b'<nu_readinglist><list>Reading<series><title>D-Genesis</title>'
            b"<chp/></series></list></nu_readinglist>"
        )
        response = self.client.post(
            reverse("parse_novelupdates_import"),
            data={
                "file": SimpleUploadedFile(
                    "nu.xml", sample, content_type="application/xml"
                )
            },
        )
        self.assertEqual(response.status_code, 200, response.data)
        entry = response.data["entries"][0]
        self.assertEqual(entry["status"], "ambiguous")
        self.assertIsNone(entry["novel"])
        self.assertEqual(len(entry["candidates"]), 2)


class HasCrawlerTests(TestCase):
    """Liveness helper behind the greyed-out Update button."""

    def setUp(self):
        from lncrawler_api.utils import crawler_registry

        self.registry = crawler_registry
        self.registry._cache.clear()
        # Resolve the crawler package path so ``patch`` can import lncrawl below.
        self.registry.has_crawler("https://warmup.invalid/__warm__")
        self.registry._cache.clear()

    def test_empty_and_non_http_are_dead(self):
        self.assertFalse(self.registry.has_crawler(""))
        self.assertFalse(self.registry.has_crawler("example.com/novel"))

    def test_live_missing_and_disabled_crawlers(self):
        from unittest.mock import patch

        live = type("Live", (), {"is_disabled": False, "disable_reason": None})
        disabled = type("Disabled", (), {"is_disabled": True, "disable_reason": None})
        dead = type("Reason", (), {"is_disabled": False, "disable_reason": "gone"})
        url = "https://example.com/x"

        with patch("lncrawl.core.sources.get_crawler_by_url", return_value=live):
            self.assertTrue(self.registry.has_crawler(url))
        self.registry._cache.clear()
        with patch("lncrawl.core.sources.get_crawler_by_url", return_value=disabled):
            self.assertFalse(self.registry.has_crawler(url))
        self.registry._cache.clear()
        with patch("lncrawl.core.sources.get_crawler_by_url", return_value=dead):
            self.assertFalse(self.registry.has_crawler(url))
        self.registry._cache.clear()
        with patch("lncrawl.core.sources.get_crawler_by_url", return_value=None):
            self.assertFalse(self.registry.has_crawler(url))

    def test_registry_failure_fails_open_and_is_not_cached(self):
        from unittest.mock import patch

        url = "https://example.com/x"
        with patch("lncrawl.core.sources.get_crawler_by_url", side_effect=RuntimeError):
            self.assertTrue(self.registry.has_crawler(url))
        live = type("Live", (), {"is_disabled": False, "disable_reason": None})
        with patch("lncrawl.core.sources.get_crawler_by_url", return_value=live):
            self.assertTrue(self.registry.has_crawler(url))


class ChatTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="chatter", password="pw")
        self.list_url = reverse("list_chat")
        self.add_url = reverse("add_chat_message")

    def _post(self, payload, authenticated=False):
        if authenticated:
            self.client.force_login(self.user)
        return self.client.post(
            self.add_url, data=json.dumps(payload), content_type="application/json"
        )

    def test_anonymous_requires_author_name(self):
        response = self._post({"message": "hello"})
        self.assertEqual(response.status_code, 400)

    def test_anonymous_can_post_with_name(self):
        response = self._post({"message": "hello", "author_name": "anon"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["author_name"], "anon")
        self.assertIsNone(response.json()["user"])

    def test_authenticated_author_name_autofilled(self):
        response = self._post({"message": "hello"}, authenticated=True)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["author_name"], "chatter")
        self.assertIsNotNone(response.json()["user"])

    def test_authenticated_author_name_cannot_be_spoofed(self):
        response = self._post(
            {"message": "hello", "author_name": "someoneelse"}, authenticated=True
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["author_name"], "chatter")

    def test_list_is_newest_first_and_paginated(self):
        for i in range(3):
            ChatMessage.objects.create(author_name="a", message=f"m{i}")
        response = self.client.get(self.list_url, {"page_size": 2})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 3)
        self.assertEqual(body["total_pages"], 2)
        self.assertEqual([m["message"] for m in body["results"]], ["m2", "m1"])

    def test_reply_carries_parent_preview(self):
        parent = self._post({"message": "parent", "author_name": "a"}).json()
        response = self._post(
            {"message": "child", "author_name": "b", "parent_id": parent["id"]}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["parent"]["id"], parent["id"])
        self.assertEqual(response.json()["parent"]["message"], "parent")

    def test_reply_to_unknown_parent_is_400(self):
        import uuid

        response = self._post(
            {"message": "child", "author_name": "b", "parent_id": str(uuid.uuid4())}
        )
        self.assertEqual(response.status_code, 400)

    def test_message_too_long_is_400(self):
        response = self._post({"message": "x" * 10001, "author_name": "a"})
        self.assertEqual(response.status_code, 400)

    def test_contains_spoiler_round_trip(self):
        response = self._post(
            {"message": "spoiled", "author_name": "a", "contains_spoiler": True}
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["contains_spoiler"])


class BoardToChatMigrationTests(TransactionTestCase):
    """Exercise the 0056 data migration, which is skipped when the board tables are empty."""

    def test_board_comments_are_copied_to_chat_messages(self):
        migrate_from = [("lncrawler_api", "0055_job_retry_count")]
        migrate_to = [("lncrawler_api", "0057_remove_board")]

        executor = MigrationExecutor(connection)
        executor.migrate(migrate_from)
        old_apps = executor.loader.project_state(migrate_from).apps
        Board = old_apps.get_model("lncrawler_api", "Board")
        Comment = old_apps.get_model("lncrawler_api", "Comment")

        user = get_user_model().objects.create_user(username="mig", password="pw")
        board = Board.objects.create(name="General", slug="general")
        parent_time = timezone.now() - timedelta(days=3)
        parent = Comment.objects.create(
            board=board,
            user_id=user.pk,
            author_name="mig",
            message="parent",
            contains_spoiler=True,
            ip_address="1.2.3.4",
            edited=True,
        )
        Comment.objects.filter(pk=parent.pk).update(created_at=parent_time)
        reply = Comment.objects.create(
            board=board,
            user_id=user.pk,
            author_name="mig",
            message="reply",
            parent_id=parent.pk,
        )
        reply_time = parent_time + timedelta(minutes=1)
        Comment.objects.filter(pk=reply.pk).update(created_at=reply_time)
        parent_pk, reply_pk = parent.pk, reply.pk

        try:
            executor = MigrationExecutor(connection)
            executor.migrate(migrate_to)
            new_apps = executor.loader.project_state(migrate_to).apps
            ChatMessage = new_apps.get_model("lncrawler_api", "ChatMessage")
            NewComment = new_apps.get_model("lncrawler_api", "Comment")

            self.assertEqual(ChatMessage.objects.count(), 2)
            self.assertFalse(
                NewComment.objects.filter(pk__in=[parent_pk, reply_pk]).exists()
            )

            copied_parent = ChatMessage.objects.get(pk=parent_pk)
            self.assertEqual(copied_parent.message, "parent")
            self.assertEqual(copied_parent.user_id, user.pk)
            self.assertEqual(copied_parent.author_name, "mig")
            self.assertTrue(copied_parent.contains_spoiler)
            self.assertEqual(copied_parent.ip_address, "1.2.3.4")
            self.assertTrue(copied_parent.edited)
            self.assertIsNone(copied_parent.parent_id)
            self.assertEqual(copied_parent.created_at, parent_time)

            copied_reply = ChatMessage.objects.get(pk=reply_pk)
            self.assertEqual(copied_reply.parent_id, parent_pk)
            self.assertEqual(copied_reply.created_at, reply_time)
        finally:
            # Restore the schema to the latest migration for subsequent tests.
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
