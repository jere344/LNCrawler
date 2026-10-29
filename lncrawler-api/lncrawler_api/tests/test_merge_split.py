"""Tests for merging and splitting novels."""

import json
import os
from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError

from django.db.models import Sum

from django.urls import reverse
from django.utils import timezone

from ..models import (
    Audiobook,
    Chapter,
    Comment,
    ExternalSource,
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

from ..services.novel_operations import dedupe_source
from ..utils import resolve_novel_slug
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

    def test_split_moves_the_audiobook_with_its_source(self):
        audiobook = Audiobook.objects.create(novel=self.novel, source=self.web_source)

        with self.captureOnCommitCallbacks(execute=True):
            new = split_novel(
                self.novel,
                [self.web_source],
                new_title="Re:Zero [Web Novel]",
                new_slug="rezero-webnovel",
                rename_title="Re:Zero [Light Novel]",
            )

        audiobook.refresh_from_db()
        self.assertEqual(audiobook.novel, new)
        self.assertEqual(audiobook.source, self.web_source)

    def test_move_sources_into_existing_novel_dedupes(self):
        target = Novel.objects.create(
            title="Re:Zero WN", slug="rezero-wn", novel_path="rezero-wn"
        )
        # The target already has a smaller copy of the same external source.
        existing = self.make_source(
            target,
            self.es_web,
            # Same work as "Re:Zero WN" (a title that names another work would
            # no longer be folded by the same-site fallback).
            "Re:Zero WN (old)",
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
        self.assertEqual(new.slug, "rezero-wn")
        self.assertEqual(new.novel_path, "rezero-wn")

        self.write_meta(self.web_source, "http://web/rezero", 2)
        updated = NovelFromSource.from_meta_json(
            os.path.join(self.tmp, "rezero-wn", "webnovel", "meta.json")
        )
        self.assertEqual(updated.novel, new)
        self.assertEqual(Novel.objects.filter(slug="rezero-wn").count(), 1)

    def _import_folder(self, folder_name, title):
        source_dir = os.path.join(self.tmp, folder_name, "webnovel")
        os.makedirs(source_dir, exist_ok=True)
        with open(
            os.path.join(source_dir, "meta.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(
                {"novel": {"title": title, "url": "http://web/hunter"}}, handle
            )
        return NovelFromSource.from_meta_json(
            os.path.join(source_dir, "meta.json")
        )

    def test_non_latin_folder_slug_is_transliterated(self):
        # A raw non-Latin folder must transliterate to a usable slug instead of
        # collapsing to a stray Latin letter ("s급 헌터" -> "s").
        source = self._import_folder("s급 헌터", "s급 헌터")
        self.assertEqual(source.novel.slug, "sgeub-heonteo")

    def test_existing_folder_with_legacy_slug_is_not_duplicated(self):
        # A novel whose stored slug was derived the old ASCII-stripping way must
        # still be found by its folder path, not duplicated, on the next import.
        legacy = Novel.objects.create(
            title="S급 헌터", slug="s", novel_path="s급 헌터"
        )
        source = self._import_folder("s급 헌터", "s급 헌터")
        self.assertEqual(source.novel, legacy)
        self.assertEqual(Novel.objects.filter(novel_path="s급 헌터").count(), 1)

    def test_legacy_row_without_novel_path_matches_by_django_slug(self):
        # Rows imported before novel_path existed have no path to match on, so
        # the Django-derived slug fallback must still reattach them.
        legacy = Novel.objects.create(
            title="Earth's Greatest Magus",
            slug="earths-greatest-magus",
            novel_path=None,
        )
        source = self._import_folder("earth's greatest magus", "Earth's Greatest Magus")
        self.assertEqual(source.novel, legacy)
        self.assertEqual(
            Novel.objects.filter(slug="earths-greatest-magus").count(), 1
        )

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


class SameSiteCoexistenceTests(MergeTestCase):
    """One novel holds the WN and LN of one site, each in its own folder."""

    def _crawl(self, novel_folder, title, url, marker):
        source_dir = os.path.join(self.tmp, novel_folder, "site")
        os.makedirs(source_dir, exist_ok=True)
        with open(os.path.join(source_dir, "marker.txt"), "w", encoding="utf-8") as handle:
            handle.write(marker)
        meta_path = os.path.join(source_dir, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(
                {"novel": {"title": title, "url": url}, "session": {"completed": True}},
                handle,
            )
        return meta_path

    def _marker(self, *parts):
        with open(os.path.join(self.tmp, *parts, "marker.txt"), encoding="utf-8") as handle:
            return handle.read()

    def test_wn_and_ln_of_one_site_coexist_and_reimport_is_stable(self):
        wn = NovelFromSource.from_meta_json(self._crawl("foo", "Foo (WN)", "http://site/wn", "wn"))
        novel = wn.novel
        # The LN crawl writes under its own novel folder and reaches the merged
        # novel through its alias, as it would after a merge.
        NovelAlias.objects.create(slug="lnfoo", novel=novel)
        ln = NovelFromSource.from_meta_json(self._crawl("lnfoo", "Foo (LN)", "http://site/ln", "ln"))

        self.assertEqual(ln.novel, novel)
        self.assertEqual(novel.sources.count(), 2)
        self.assertEqual(ExternalSource.objects.filter(source_name="site").count(), 1)
        self.assertEqual(wn.source_path, os.path.join("foo", "site"))
        self.assertEqual(ln.source_path, os.path.join("foo", "site [light-novel]"))
        self.assertNotEqual(wn.source_slug, ln.source_slug)
        self.assertEqual(self._marker("foo", "site"), "wn")
        self.assertEqual(self._marker("foo", "site [light-novel]"), "ln")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "lnfoo")))

        # Re-importing each folder resolves to the same row and keeps its folder.
        wn_again = NovelFromSource.from_meta_json(
            os.path.join(self.tmp, "foo", "site", "meta.json")
        )
        ln_again = NovelFromSource.from_meta_json(
            os.path.join(self.tmp, "foo", "site [light-novel]", "meta.json")
        )
        self.assertEqual(wn_again.pk, wn.pk)
        self.assertEqual(ln_again.pk, ln.pk)
        self.assertEqual(novel.sources.count(), 2)
        self.assertEqual(ln_again.source_path, os.path.join("foo", "site [light-novel]"))
        self.assertEqual(self._marker("foo", "site [light-novel]"), "ln")

        # A mirror that changed the LN URL still finds the LN row by its title.
        ln_meta = os.path.join(self.tmp, "foo", "site [light-novel]", "meta.json")
        with open(ln_meta, "w", encoding="utf-8") as handle:
            json.dump(
                {"novel": {"title": "Foo (LN)", "url": "http://mirror/ln"},
                 "session": {"completed": True}},
                handle,
            )
        mirror = NovelFromSource.from_meta_json(ln_meta)
        self.assertEqual(mirror.pk, ln.pk)
        self.assertEqual(novel.sources.count(), 2)


    def test_site_folder_helpers_name_coexisting_sources(self):
        from ..utils import lncrawler_paths

        self.assertEqual(lncrawler_paths.site_name_from_folder("foo [ln]"), "foo")
        self.assertEqual(lncrawler_paths.site_name_from_folder("foo [2]"), "foo")
        self.assertEqual(lncrawler_paths.site_name_from_folder("foo"), "foo")

        novel_dir = os.path.join(self.tmp, "foo")
        self.assertEqual(
            lncrawler_paths.free_source_folder(novel_dir, "site", "Web Novel", {"site"}),
            "site [web-novel]",
        )
        self.assertEqual(
            lncrawler_paths.free_source_folder(novel_dir, "site", "Official translation", {"site"}),
            "site [official-translation]",
        )
        # No edition, or an edition whose folder is already on disk: a number.
        self.assertEqual(
            lncrawler_paths.free_source_folder(novel_dir, "site", "", {"site"}),
            "site [2]",
        )
        os.makedirs(os.path.join(novel_dir, "site [light-novel]"))
        self.assertEqual(
            lncrawler_paths.free_source_folder(novel_dir, "site", "Light Novel", {"site"}),
            "site [2]",
        )

    def test_edition_is_exposed_on_the_source_card(self):
        from ..serializers import NovelSourceSerializer

        novel = Novel.objects.create(title="Foo", slug="foo-edition", novel_path="foo")
        external = ExternalSource.objects.create(source_name="site-edition")
        ln = NovelFromSource.objects.create(
            novel=novel, external_source=external, title="Foo (LN)", edition="Light Novel",
            source_url="http://e/ln", source_slug="site-edition-ln",
        )
        unknown = NovelFromSource.objects.create(
            novel=novel, external_source=external, title="Foo",
            source_url="http://e/none", source_slug="site-edition-none",
        )
        self.assertEqual(NovelSourceSerializer(ln, profile="card").data["edition"], "Light Novel")
        self.assertIsNone(NovelSourceSerializer(unknown, profile="card").data["edition"])


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


class MergeConflictRulesTests(MergeTestCase):
    """Rules a merge must follow when both novels hold the same user's data."""

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
        self.user = get_user_model().objects.create_user(
            username="reader", email="reader@example.com", password="x"
        )
        self.other = get_user_model().objects.create_user(
            username="other", email="other@example.com", password="x"
        )

    def test_same_user_rated_both_novels_keeps_the_newer_rating(self):
        now = timezone.now()
        NovelRating.objects.create(novel=self.target, user=self.user, rating=2)
        NovelRating.objects.create(novel=self.duplicate, user=self.user, rating=5)
        NovelRating.objects.filter(novel=self.target, user=self.user).update(
            updated_at=now - timedelta(days=3)
        )
        # Second reader: the target's rating is the newer one and must survive.
        NovelRating.objects.create(novel=self.target, user=self.other, rating=1)
        NovelRating.objects.create(novel=self.duplicate, user=self.other, rating=4)
        NovelRating.objects.filter(novel=self.duplicate, user=self.other).update(
            updated_at=now - timedelta(days=3)
        )

        merge_novels(self.duplicate, self.target, move_files=True)

        self.assertEqual(
            NovelRating.objects.get(novel=self.target, user=self.user).rating, 5
        )
        self.assertEqual(
            NovelRating.objects.get(novel=self.target, user=self.other).rating, 1
        )
        self.assertEqual(NovelRating.objects.filter(novel=self.target).count(), 2)

    def test_anonymous_ratings_still_dedupe_by_ip(self):
        NovelRating.objects.create(novel=self.target, ip_address="1.1.1.1", rating=2)
        NovelRating.objects.create(novel=self.duplicate, ip_address="1.1.1.1", rating=5)
        NovelRating.objects.create(novel=self.duplicate, ip_address="2.2.2.2", rating=4)
        NovelRating.objects.create(novel=self.duplicate, ip_address=None, rating=3)

        merge_novels(self.duplicate, self.target, move_files=True)

        anonymous = NovelRating.objects.filter(novel=self.target, user__isnull=True)
        # The target keeps its row for 1.1.1.1; the NULL-IP row always moves.
        self.assertEqual(anonymous.count(), 3)
        self.assertEqual(anonymous.get(ip_address="1.1.1.1").rating, 2)
        self.assertEqual(anonymous.get(ip_address="2.2.2.2").rating, 4)
        self.assertTrue(anonymous.filter(ip_address__isnull=True, rating=3).exists())

    def test_reading_history_keeps_the_most_recent_row_on_either_side(self):
        target_src = self.make_source(
            self.target, self.es_a, "LOTM", "http://a/lotm", "lotm", "novelfull"
        )
        dup_src = self.make_source(
            self.duplicate, self.es_b, "lom", "http://b/lom", "lom", "novelbin"
        )
        now = timezone.now()
        # First reader: the duplicate side was read most recently.
        ReadingHistory.objects.create(user=self.user, novel=self.target, source=target_src)
        dup_history = ReadingHistory.objects.create(
            user=self.user, novel=self.duplicate, source=dup_src
        )
        ReadingHistory.objects.filter(user=self.user, novel=self.target).update(
            last_read_at=now - timedelta(days=2)
        )
        ReadingHistory.objects.filter(pk=dup_history.pk).update(last_read_at=now)
        # Second reader: the target side is the more recent one.
        ReadingHistory.objects.create(user=self.other, novel=self.target, source=target_src)
        ReadingHistory.objects.create(user=self.other, novel=self.duplicate, source=dup_src)
        ReadingHistory.objects.filter(user=self.other, novel=self.duplicate).update(
            last_read_at=now - timedelta(days=2)
        )

        merge_novels(self.duplicate, self.target, move_files=True)

        survivor = ReadingHistory.objects.get(user=self.user)
        self.assertEqual(survivor.novel, self.target)
        self.assertEqual(survivor.source, dup_src)
        # A queryset move must not bump last_read_at to the merge time.
        self.assertEqual(survivor.last_read_at, now)
        self.assertEqual(
            ReadingHistory.objects.get(user=self.other).source, target_src
        )

    def test_newer_review_wins_on_either_side(self):
        now = timezone.now()
        Review.objects.create(
            novel=self.target, user=self.user, title="old", content="x", rating=2
        )
        Review.objects.create(
            novel=self.duplicate, user=self.user, title="new", content="y", rating=5
        )
        Review.objects.create(
            novel=self.target, user=self.other, title="t", content="z", rating=1
        )
        Review.objects.create(
            novel=self.duplicate, user=self.other, title="d", content="w", rating=4
        )
        Review.objects.filter(novel=self.target, user=self.user).update(
            updated_at=now - timedelta(days=2)
        )
        Review.objects.filter(novel=self.duplicate, user=self.user).update(updated_at=now)
        Review.objects.filter(novel=self.target, user=self.other).update(updated_at=now)
        Review.objects.filter(novel=self.duplicate, user=self.other).update(
            updated_at=now - timedelta(days=2)
        )

        merge_novels(self.duplicate, self.target, move_files=True)

        self.assertEqual(Review.objects.get(novel=self.target, user=self.user).rating, 5)
        self.assertEqual(Review.objects.get(novel=self.target, user=self.other).rating, 1)
        self.assertEqual(Review.objects.filter(novel=self.target).count(), 2)

    def test_same_site_different_works_coexist_after_merge(self):
        target_src = self.make_source(
            self.target, self.es_a, "Foo (WN)", "http://a/wn", "lotm", "novelfull", 2
        )
        dup_src = self.make_source(
            self.duplicate, self.es_a, "Foo (LN)", "http://a/ln", "lom", "novelfull", 1
        )

        with self.captureOnCommitCallbacks(execute=True):
            merge_novels(self.duplicate, self.target, move_files=True)

        self.assertFalse(Novel.objects.filter(slug="lom").exists())
        self.assertEqual(self.target.sources.count(), 2)
        target_src.refresh_from_db()
        dup_src.refresh_from_db()
        self.assertEqual(dup_src.novel, self.target)
        # Each work keeps its own folder, so the files are never mixed.
        self.assertEqual(target_src.source_path, os.path.join("lotm", "novelfull"))
        self.assertEqual(dup_src.source_path, os.path.join("lotm", "novelfull [light-novel]"))
        self.assertNotEqual(target_src.source_slug, dup_src.source_slug)
        self.assertEqual(
            len(os.listdir(os.path.join(self.tmp, "lotm", "novelfull", "json"))), 2
        )
        self.assertEqual(
            len(os.listdir(os.path.join(self.tmp, "lotm", "novelfull [light-novel]", "json"))), 1
        )
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "lom")))

    def test_same_site_different_works_coexist_after_split_into_existing_novel(self):
        self.make_source(
            self.target, self.es_a, "Foo (WN)", "http://a/wn", "lotm", "novelfull", 1
        )
        moving = self.make_source(
            self.duplicate, self.es_a, "Foo (LN)", "http://a/ln", "lom", "novelfull", 1
        )
        self.make_source(
            self.duplicate, self.es_b, "Other", "http://b/x", "lom", "novelbin", 1
        )

        move_sources(self.duplicate, [moving], self.target)

        moving.refresh_from_db()
        self.assertEqual(moving.novel, self.target)
        self.assertEqual(moving.source_path, os.path.join("lotm", "novelfull [light-novel]"))
        self.assertTrue(
            os.path.isdir(os.path.join(self.tmp, "lotm", "novelfull [light-novel]"))
        )
        self.assertEqual(self.target.sources.count(), 2)

    def test_compatible_titles_on_the_same_site_still_dedupe(self):
        self.make_source(
            self.target, self.es_a, "Foo (WN)", "http://a/wn", "lotm", "novelfull", 1
        )
        self.make_source(
            self.duplicate, self.es_a, "Foo [WN]", "http://a/mirror", "lom", "novelfull", 2
        )

        merge_novels(self.duplicate, self.target, move_files=True)

        survivors = self.target.sources.all()
        self.assertEqual(survivors.count(), 1)
        self.assertEqual(survivors.get().chapters.count(), 2)

    def test_source_slug_collision_on_move_gets_a_suffix(self):
        self.make_source(
            self.target, self.es_b, "LOTM", "http://b/lotm", "lotm", "novelbin"
        )
        # Another work of the same site, in a folder with the target's name: the
        # move takes a free "[2]" folder and the slug derived from it is suffixed.
        moved = self.make_source(
            self.duplicate, self.es_b, "Other Story", "http://b/other", "lom", "novelbin"
        )

        merge_novels(self.duplicate, self.target, move_files=True)

        moved.refresh_from_db()
        self.assertEqual(moved.novel, self.target)
        self.assertEqual(moved.source_path, os.path.join("lotm", "novelbin [2]"))
        self.assertEqual(moved.source_slug, "novelbin-2")


class MergeConflictAdminTests(MergeTestCase):
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
            self.target, external, "Foo (WN)", "http://a/wn", "lotm", "novelfull", 1
        )
        self.make_source(
            self.duplicate, external, "Foo (LN)", "http://a/ln", "lom", "novelfull", 1
        )
        self.admin = get_user_model().objects.create_superuser(
            username="admin", password="x"
        )
        self.client.force_login(self.admin)

    def test_preview_offers_the_merge_for_same_site_works(self):
        url = reverse("admin:lncrawler_api_novel_merge")
        response = self.client.post(
            url, {"source_novel": self.duplicate.pk, "target_novel": self.target.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "lists both as separate works")
        self.assertContains(response, 'name="confirm"')


class DedupeChapterDataTests(MergeTestCase):
    """Dedupe keeps the loser's comments and reading position on the winner."""

    def setUp(self):
        super().setUp()
        self.target = Novel.objects.create(
            title="Lord of the Mysteries", slug="lotm", novel_path="lotm"
        )
        self.duplicate = Novel.objects.create(
            title="Lord of Mysteries", slug="lom", novel_path="lom"
        )
        external = ExternalSource.objects.create(source_name="novelfull")
        self.winner = self.make_source(
            self.target, external, "LOTM", "http://a/w", "lotm", "novelfull", 2
        )
        self.loser = self.make_source(
            self.duplicate, external, "lom", "http://a/l", "lom", "novelfull", 2
        )
        # Chapter 2 of the loser shares its url with the winner's chapter 2;
        # chapter 1 only matches by number, and chapter 3 has no counterpart.
        self.loser.chapters.filter(chapter_id=2).update(url="http://a/w/ch2")
        self.loser_orphan = Chapter.objects.create(
            novel_from_source=self.loser, chapter_id=3, url="http://a/l/ch3", title="Chapter 3"
        )
        self.user = get_user_model().objects.create_user(username="reader", password="x")

    def test_comments_and_reading_position_follow_the_winner_chapter(self):
        loser_ch1 = self.loser.chapters.get(chapter_id=1)
        loser_ch2 = self.loser.chapters.get(chapter_id=2)
        winner_ch1 = self.winner.chapters.get(chapter_id=1)
        winner_ch2 = self.winner.chapters.get(chapter_id=2)

        on_one = Comment.objects.create(chapter=loser_ch1, author_name="a", message="one")
        on_two = Comment.objects.create(chapter=loser_ch2, author_name="a", message="two")
        on_three = Comment.objects.create(
            chapter=self.loser_orphan, author_name="a", message="three"
        )
        history = ReadingHistory.objects.create(
            user=self.user, novel=self.duplicate, source=self.loser,
            last_read_chapter=loser_ch2,
        )

        dedupe_source(self.loser, self.winner, move_files=False, dest_novel=self.target)

        on_one.refresh_from_db()
        on_two.refresh_from_db()
        self.assertEqual(on_one.chapter_id, winner_ch1.pk)
        self.assertEqual(on_two.chapter_id, winner_ch2.pk)

        history.refresh_from_db()
        self.assertEqual(history.source_id, self.winner.pk)
        self.assertEqual(history.last_read_chapter_id, winner_ch2.pk)

        # No winner chapter matches: the comment survives as a novel comment.
        on_three.refresh_from_db()
        self.assertIsNone(on_three.chapter_id)
        self.assertEqual(on_three.novel_id, self.target.pk)

        self.assertFalse(NovelFromSource.objects.filter(pk=self.loser.pk).exists())
        self.assertEqual(self.winner.chapters.count(), 2)


class MoveSourcesCommentTests(MergeTestCase):
    """A deduped loser's unmatched comments land on the destination novel (M2)."""

    def test_unmatched_comment_of_a_deduped_loser_follows_the_destination(self):
        origin = Novel.objects.create(title="Re:Zero", slug="rezero", novel_path="rezero")
        target = Novel.objects.create(
            title="Re:Zero WN", slug="rezero-wn", novel_path="rezero-wn"
        )
        web = ExternalSource.objects.create(source_name="webnovel")
        # The incoming copy is the more complete one (2 chapters against 1), so it
        # wins the dedupe while it still belongs to the original novel.
        incoming = self.make_source(
            origin, web, "Re:Zero WN", "http://web/rezero", "rezero", "webnovel", 2
        )
        self.make_source(
            origin, ExternalSource.objects.create(source_name="lightnovel"),
            "Re:Zero LN", "http://ln/rezero", "rezero", "lightnovel", 1,
        )
        loser = self.make_source(
            target, web, "Re:Zero WN (old)", "http://old/rezero", "rezero-wn", "webnovel", 0
        )
        # Chapter 5 has no counterpart in the winner (no url, no number match).
        orphan = Chapter.objects.create(
            novel_from_source=loser, chapter_id=5, url="http://old/rezero/ch5",
            title="Chapter 5",
        )
        comment = Comment.objects.create(
            chapter=orphan, author_name="anon", message="orphan comment"
        )

        move_sources(origin, [incoming], target)

        comment.refresh_from_db()
        self.assertIsNone(comment.chapter_id)
        self.assertEqual(comment.novel_id, target.pk)
        self.assertFalse(NovelFromSource.objects.filter(pk=loser.pk).exists())
        incoming.refresh_from_db()
        self.assertEqual(incoming.novel_id, target.pk)

        origin.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual(target.comment_count, 1)
        self.assertEqual(origin.comment_count, 0)


class FileJournalTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.target = Novel.objects.create(
            title="Lord of the Mysteries", slug="lotm", novel_path="lotm"
        )
        self.duplicate = Novel.objects.create(
            title="Lord of Mysteries", slug="lom", novel_path="lom"
        )
        self.first = self.make_source(
            self.duplicate, ExternalSource.objects.create(source_name="site-a"),
            "Alpha", "http://a/x", "lom", "site-a", 1,
        )
        self.second = self.make_source(
            self.duplicate, ExternalSource.objects.create(source_name="site-b"),
            "Beta", "http://b/x", "lom", "site-b", 1,
        )

    def test_failed_second_move_restores_rows_and_the_first_folder(self):
        real_rename = os.rename
        calls = []

        def flaky_rename(src, dst):
            calls.append((src, dst))
            if len(calls) == 2:
                raise OSError("simulated failure")
            return real_rename(src, dst)

        with mock.patch("lncrawler_api.services.novel_operations.os.rename",
                        side_effect=flaky_rename):
            with self.assertRaises(MergeError):
                merge_novels(self.duplicate, self.target, move_files=True)

        self.assertEqual(len(calls), 3)  # two moves, then the undo of the first
        self.assertTrue(Novel.objects.filter(slug="lom").exists())
        self.assertFalse(NovelAlias.objects.filter(slug="lom").exists())
        for source in (self.first, self.second):
            source.refresh_from_db()
            self.assertEqual(source.novel, self.duplicate)
        self.assertEqual(self.first.source_path, "lom/site-a")
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "lom", "site-a")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "lom", "site-b")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "lotm", "site-a")))


class MergeRollbackTests(MergeTestCase):
    """A database failure after a folder move reverses both."""

    def setUp(self):
        super().setUp()
        self.target = Novel.objects.create(
            title="Lord of the Mysteries", slug="lotm", novel_path="lotm"
        )
        self.duplicate = Novel.objects.create(
            title="Lord of Mysteries", slug="lom", novel_path="lom"
        )
        self.first = self.make_source(
            self.duplicate, ExternalSource.objects.create(source_name="site-a"),
            "Alpha", "http://a/x", "lom", "site-a", 1,
        )
        self.second = self.make_source(
            self.duplicate, ExternalSource.objects.create(source_name="site-b"),
            "Beta", "http://b/x", "lom", "site-b", 1,
        )

    def test_failed_save_after_a_move_restores_the_folder_and_the_rows(self):
        with mock.patch.object(
            NovelFromSource, "save", side_effect=IntegrityError("simulated")
        ):
            with self.assertRaises(IntegrityError):
                merge_novels(self.duplicate, self.target, move_files=True)

        self.assertTrue(Novel.objects.filter(slug="lom").exists())
        self.assertFalse(NovelAlias.objects.filter(slug="lom").exists())
        for source, folder in ((self.first, "site-a"), (self.second, "site-b")):
            source.refresh_from_db()
            self.assertEqual(source.novel, self.duplicate)
            self.assertEqual(source.source_path, os.path.join("lom", folder))
            self.assertTrue(os.path.isdir(os.path.join(self.tmp, "lom", folder)))
            self.assertFalse(os.path.exists(os.path.join(self.tmp, "lotm", folder)))


class ReplacedFolderTrashTests(MergeTestCase):
    def test_replaced_copy_is_trashed_until_commit_then_emptied(self):
        target = Novel.objects.create(title="Lord of the Mysteries", slug="lotm", novel_path="lotm")
        duplicate = Novel.objects.create(title="Lord of Mysteries", slug="lom", novel_path="lom")
        external = ExternalSource.objects.create(source_name="novelfull")
        self.make_source(target, external, "LOTM", "http://a/w", "lotm", "novelfull", 2)
        self.make_source(duplicate, external, "lom", "http://a/l", "lom", "novelfull", 3)
        trash = os.path.join(self.tmp, ".trash")

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            merge_novels(duplicate, target, move_files=True)

        # Before commit the replaced copy is parked in the trash, not deleted.
        parked = os.listdir(trash)
        self.assertEqual(len(parked), 1)
        self.assertTrue(os.path.isdir(os.path.join(trash, parked[0], "json")))
        # The incoming, more complete copy now sits at the canonical path.
        self.assertTrue(os.path.isfile(
            os.path.join(self.tmp, "lotm", "novelfull", "json", "00003.json")
        ))

        for callback in callbacks:
            callback()
        self.assertEqual(os.listdir(trash), [])
