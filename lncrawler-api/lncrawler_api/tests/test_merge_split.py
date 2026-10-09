"""Tests for merging and splitting novels."""

import json
import os
from datetime import date

from django.contrib.auth import get_user_model

from django.db.models import Sum

from django.urls import reverse

from ..models import (
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
    ReadingListItem,
    Review,
    SourceVote,
    WeeklySourceView,
)

from ..services import (
    MergeError,
    SplitError,
    build_merge_plan,
    move_sources,
    merge_novels,
    split_novel,
)

from ..utils import resolve_novel_slug
from .helpers import MergeTestCase, write_chapter

from .helpers import MergeTestCase, write_chapter


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


class ChapterReimportTests(MergeTestCase):
    def test_renumbered_chapters_do_not_collide(self):
        novel = Novel.objects.create(
            title="Renumbered", slug="renumbered", novel_path="renumbered"
        )
        external = ExternalSource.objects.create(source_name="renumber-site")
        source = self.make_source(
            novel, external, "Renumbered", "http://r/s", "renumbered",
            "renumber-site", 3,
        )
        # A new chapter prepended to the list shifts every id up by one while
        # the urls stay put, so url matching must move each existing row.
        comment = Comment.objects.create(
            chapter=source.chapters.get(chapter_id=1), author_name="anon", message="hi"
        )
        meta_path = os.path.join(source.absolute_source_path, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "novel": {
                        "title": "Renumbered",
                        "url": "http://r/s",
                        "chapters": [
                            {"id": n + 1, "url": f"http://r/s/ch{n}", "title": f"Chapter {n}"}
                            for n in (1, 2, 3)
                        ],
                    }
                },
                handle,
            )

        updated = NovelFromSource.from_meta_json(meta_path)

        self.assertEqual(updated.pk, source.pk)
        self.assertEqual(
            sorted(updated.chapters.values_list("chapter_id", flat=True)), [2, 3, 4]
        )
        # Comments follow the row, which is now chapter 2.
        comment.refresh_from_db()
        self.assertEqual(comment.chapter.chapter_id, 2)

    def test_removed_chapter_keeps_comments_and_progress(self):
        novel = Novel.objects.create(
            title="Removed", slug="removed", novel_path="removed"
        )
        external = ExternalSource.objects.create(source_name="removed-site")
        source = self.make_source(
            novel, external, "Removed", "http://x/s", "removed",
            "removed-site", 3,
        )
        removed = source.chapters.get(chapter_id=2)
        comment = Comment.objects.create(
            chapter=removed, author_name="anon", message="hi"
        )
        user = get_user_model().objects.create_user(username="reader", password="x")
        history = ReadingHistory.objects.create(
            user=user, novel=novel, source=source, last_read_chapter=removed
        )
        # Chapter 2 is gone and the list renumbers down: chapter 3 becomes
        # chapter 2, reusing the removed row's slot.
        meta_path = os.path.join(source.absolute_source_path, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "novel": {
                        "title": "Removed",
                        "url": "http://x/s",
                        "chapters": [
                            {"id": 1, "url": "http://x/s/ch1", "title": "Chapter 1"},
                            {"id": 2, "url": "http://x/s/ch3", "title": "Chapter 3"},
                        ],
                    }
                },
                handle,
            )

        updated = NovelFromSource.from_meta_json(meta_path)

        self.assertEqual(
            sorted(updated.chapters.values_list("chapter_id", flat=True)), [1, 2]
        )
        # The removed chapter's comment and progress must survive, repointed at
        # the chapter that took over its slot (url /ch3).
        comment.refresh_from_db()
        self.assertEqual(comment.chapter.chapter_id, 2)
        self.assertEqual(comment.chapter.url, "http://x/s/ch3")
        history.refresh_from_db()
        self.assertEqual(history.last_read_chapter.chapter_id, 2)


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

    def test_same_url_is_replaced_by_the_more_complete_copy(self):
        # Both novels carry the SAME source_url, so the incoming (more complete)
        # copy must fold the target's copy first, or repointing collides on
        # (novel, source_url).
        same_url = "http://a/same"
        target = Novel.objects.create(title="Same", slug="same-t", novel_path="same-t")
        dup = Novel.objects.create(title="Same", slug="same-d", novel_path="same-d")
        existing = self.make_source(
            target, self.external, "old", same_url, "same-t", "novelfull", 1
        )
        incoming = self.make_source(
            dup, self.external, "new", same_url, "same-d", "novelfull", 4
        )

        merge_novels(dup, target, move_files=False)

        survivors = target.sources.filter(external_source=self.external)
        self.assertEqual(survivors.count(), 1)
        self.assertEqual(survivors.get().pk, incoming.pk)
        self.assertEqual(survivors.get().chapters.count(), 4)
        self.assertFalse(NovelFromSource.objects.filter(pk=existing.pk).exists())


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
        from ..admin.novel_admin import SplitNovelForm

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
