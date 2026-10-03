import json
import os
import shutil
import tempfile
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.cache import cache
from django.db.models import Sum
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    Chapter,
    Comment,
    ExternalSource,
    FeaturedNovel,
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
        self.assertEqual(novel["prefered_source"]["language"], "fr")

    def test_prefered_source_falls_back_when_language_absent(self):
        # English source (worst votes) wins only because fr is excluded.
        response = self.client.get(reverse("home_page"), {"languages": "en"})
        novel = next(n for n in response.data["top_novels"] if n["title"] == "Bilingue")
        self.assertEqual(novel["prefered_source"]["language"], "en")


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
        self.assertEqual(novel["prefered_source"]["language"], "fr")
        self.assertEqual(novel["reading_source"]["language"], "en")
        self.assertEqual(novel["reading_source"]["title"], "English")

    def test_reading_source_absent_for_anonymous(self):
        response = self.client.get(reverse("home_page"))
        self.assertIsNone(self._novel(response)["reading_source"])


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
