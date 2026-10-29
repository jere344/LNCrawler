"""Audiobooks phase 1: word counts, cutting parts, the part queue, and the admin."""

import json
import os
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..models import (
    Audiobook,
    AudiobookChapter,
    AudiobookPart,
    AudiobookWorker,
    Chapter,
    ExternalSource,
    Novel,
    NovelFromSource,
)
from ..services import audiobook_service as svc
from ..services.novel_operations import file_journal, move_source_to_novel
from .helpers import MergeTestCase


def body_of(words):
    """An HTML chapter body with exactly ``words`` words."""
    return f"<p>{' '.join(['word'] * words)}</p>"


class AudiobookBase(MergeTestCase):
    """One novel with a source folder under the test output path."""

    def setUp(self):
        super().setUp()
        self.novel = Novel.objects.create(title="Foo", slug="foo", novel_path="foo")

    def make_source(self, name="site", language="en", status="Ongoing", last_update=None):
        source_path = os.path.join("foo", name)
        os.makedirs(os.path.join(self.tmp, source_path), exist_ok=True)
        return NovelFromSource.objects.create(
            novel=self.novel,
            external_source=ExternalSource.objects.create(source_name=name),
            title="Foo",
            source_url=f"http://{name}/1",
            source_path=source_path,
            source_slug=name,
            language=language,
            status=status,
            last_chapter_update=last_update,
        )

    def add_chapters(self, source, words, first_id=1, has_content=True, write_files=True):
        """One chapter per entry of ``words``: a body file of that many words, and a row."""
        json_dir = os.path.join(source.absolute_source_path, "json")
        os.makedirs(json_dir, exist_ok=True)
        for offset, count in enumerate(words):
            number = first_id + offset
            if write_files:
                with open(os.path.join(json_dir, f"{number:05}.json"), "w", encoding="utf-8") as handle:
                    json.dump({"title": f"Chapter {number}", "body": body_of(count)}, handle)
            Chapter.objects.create(
                novel_from_source=source,
                chapter_id=number,
                url=f"{source.source_url}/{number}",
                title=f"Chapter {number}",
                has_content=has_content,
            )
        return list(source.chapters.order_by("chapter_id"))

    def make_audiobook(self, source):
        return Audiobook.objects.create(novel=self.novel, source=source)

    def make_part(self, audiobook, index=1, **fields):
        defaults = {
            "chapter_start": 1,
            "chapter_end": 1,
            "word_count": 100,
        }
        return AudiobookPart.objects.create(audiobook=audiobook, index=index, **{**defaults, **fields})


class CountWordsTests(SimpleTestCase):
    def test_tags_are_not_counted(self):
        self.assertEqual(svc.count_words("<h1>Title</h1><p>one two <em>three</em></p>"), 4)

    def test_entities_are_unescaped(self):
        self.assertEqual(svc.count_words("<p>Tom &amp; Jerry&nbsp;wins</p>"), 3)

    def test_apostrophes_stay_inside_a_word(self):
        self.assertEqual(svc.count_words("<p>Don’t stop, it's fine</p>"), 4)

    def test_empty_body(self):
        self.assertEqual(svc.count_words(""), 0)


class EnsureWordCountsTests(AudiobookBase):
    def test_fills_nulls_from_the_body(self):
        source = self.make_source()
        chapter = self.add_chapters(source, [5])[0]

        svc.ensure_word_counts([chapter])

        chapter.refresh_from_db()
        self.assertEqual(chapter.word_count, 5)

    def test_missing_file_stays_none(self):
        source = self.make_source()
        chapter = self.add_chapters(source, [5], write_files=False)[0]

        svc.ensure_word_counts([chapter])

        chapter.refresh_from_db()
        self.assertIsNone(chapter.word_count)

    def test_file_with_empty_body_counts_zero(self):
        source = self.make_source()
        chapter = self.add_chapters(source, [0])[0]

        svc.ensure_word_counts([chapter])

        chapter.refresh_from_db()
        self.assertEqual(chapter.word_count, 0)

    def test_existing_count_is_left_alone(self):
        source = self.make_source()
        chapter = self.add_chapters(source, [5])[0]
        Chapter.objects.filter(pk=chapter.pk).update(word_count=99)
        chapter.refresh_from_db()

        svc.ensure_word_counts([chapter])

        chapter.refresh_from_db()
        self.assertEqual(chapter.word_count, 99)


class ReimportWordCountTests(AudiobookBase):
    """``from_meta_json`` clears a word count only when the text it counted may have changed."""

    def import_meta(self, chapters):
        source_dir = os.path.join(self.tmp, "foo", "site")
        os.makedirs(source_dir, exist_ok=True)
        meta_path = os.path.join(source_dir, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "novel": {"title": "Foo", "url": "http://site/foo", "chapters": chapters},
                    "session": {"completed": True},
                },
                handle,
            )
        return NovelFromSource.from_meta_json(meta_path)

    def counted_chapter(self, url="http://site/1"):
        Chapter.objects.update(word_count=42)
        return Chapter.objects.get(url=url)

    def test_plain_reimport_keeps_word_count(self):
        chapter = {"id": 1, "url": "http://site/1", "title": "C1", "success": True}
        self.import_meta([chapter])
        self.counted_chapter()

        self.import_meta([chapter])

        self.assertEqual(Chapter.objects.get().word_count, 42)

    def test_changed_url_resets_word_count(self):
        self.import_meta([{"id": 1, "url": "http://site/1", "title": "C1", "success": True}])
        self.counted_chapter()

        self.import_meta([{"id": 1, "url": "http://site/1-moved", "title": "C1", "success": True}])

        self.assertIsNone(Chapter.objects.get().word_count)

    def test_content_appearing_resets_word_count(self):
        self.import_meta([{"id": 1, "url": "http://site/1", "title": "C1", "success": False}])
        self.assertFalse(Chapter.objects.get().has_content)
        self.counted_chapter()

        self.import_meta([{"id": 1, "url": "http://site/1", "title": "C1", "success": True}])

        chapter = Chapter.objects.get()
        self.assertTrue(chapter.has_content)
        self.assertIsNone(chapter.word_count)

    def test_meta_word_count_is_stored_on_a_new_row(self):
        self.import_meta([{"id": 1, "url": "http://site/1", "title": "C1", "success": True, "word_count": 321}])

        self.assertEqual(Chapter.objects.get().word_count, 321)

    def test_meta_word_count_overrides_the_reset_on_an_existing_row(self):
        self.import_meta([{"id": 1, "url": "http://site/1", "title": "C1", "success": True}])
        self.counted_chapter()

        self.import_meta([{"id": 1, "url": "http://site/1-moved", "title": "C1", "success": True, "word_count": 99}])

        self.assertEqual(Chapter.objects.get().word_count, 99)


class PickSourceTests(AudiobookBase):
    def test_english_source_with_most_content_wins(self):
        small = self.make_source("small")
        big = self.make_source("big")
        self.add_chapters(small, [10, 10], write_files=False)
        self.add_chapters(big, [10, 10, 10], write_files=False)
        self.add_chapters(big, [10], first_id=10, has_content=False, write_files=False)
        french = self.make_source("fr", language="fr")
        self.add_chapters(french, [10] * 9, write_files=False)

        self.assertEqual(svc.pick_source(self.novel), big)

    def test_none_without_an_english_source(self):
        self.make_source("fr", language="fr")

        self.assertIsNone(svc.pick_source(self.novel))

    def test_best_vote_score_beats_more_chapters(self):
        many = self.make_source("many")
        self.add_chapters(many, [10] * 5, write_files=False)
        liked = self.make_source("liked")
        self.add_chapters(liked, [10], write_files=False)
        NovelFromSource.objects.filter(pk=liked.pk).update(upvotes=5, downvotes=0)

        self.assertEqual(svc.pick_source(self.novel), liked)

    def test_language_filter_picks_the_source_of_that_language(self):
        english = self.make_source()
        self.add_chapters(english, [10], write_files=False)
        french = self.make_source("fr", language="fr")
        self.add_chapters(french, [10], write_files=False)

        self.assertEqual(svc.pick_source(self.novel, "fr"), french)
        self.assertEqual(svc.pick_source(self.novel), english)


class AudiobookUniquenessTests(AudiobookBase):
    def test_one_audiobook_per_novel_and_language(self):
        english = self.make_source()
        french = self.make_source("fr", language="fr")
        self.make_audiobook(english)
        Audiobook.objects.create(novel=self.novel, source=french, language="fr")

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_audiobook(english)

    def test_get_or_create_returns_the_existing_book(self):
        english = self.make_source()
        audiobook = self.make_audiobook(english)

        found, created = svc.get_or_create_audiobook(self.novel)

        self.assertFalse(created)
        self.assertEqual(found.pk, audiobook.pk)


class ContentHashTests(AudiobookBase):
    def test_missing_file_gives_no_hash(self):
        source = self.make_source()
        chapters = self.add_chapters(source, [5, 5])
        os.remove(os.path.join(source.absolute_source_path, "json", "00002.json"))

        self.assertIsNone(svc.content_hash(chapters))

    def test_same_text_gives_the_same_hash(self):
        source = self.make_source()
        chapters = self.add_chapters(source, [5, 5])

        self.assertEqual(svc.content_hash(chapters), svc.content_hash(chapters))


@override_settings(AUDIOBOOK_PART_WORDS=1000)
class CutNextPartTests(AudiobookBase):
    # Chapters 1-6: 400, 400, 300, 500, a 0-word chapter, 100 words.
    WORDS = [400, 400, 300, 500, 0, 100]

    def setUp(self):
        super().setUp()
        self.source = self.make_source()
        self.add_chapters(self.source, self.WORDS)
        self.audiobook = self.make_audiobook(self.source)

    def ids(self, cut):
        return [ch.chapter_id for ch in cut["chapters"]]

    def test_stops_before_exceeding_the_target(self):
        cut = svc.cut_next_part(self.audiobook)

        self.assertEqual(self.ids(cut), [1, 2])
        self.assertEqual(cut["word_count"], 800)
        self.assertFalse(cut["is_tail"])

    def test_over_long_chapter_is_its_own_part(self):
        self.source.chapters.all().delete()
        self.add_chapters(self.source, [1500, 200])

        cut = svc.cut_next_part(self.audiobook)

        self.assertEqual(self.ids(cut), [1])
        self.assertEqual(cut["word_count"], 1500)

    def test_zero_word_chapters_are_skipped(self):
        self.source.chapters.all().delete()
        self.add_chapters(self.source, [0, 500, 0, 600])

        cut = svc.cut_next_part(self.audiobook)

        self.assertEqual(self.ids(cut), [2])

    def test_tail_needs_allow_tail_or_a_settled_completed_source(self):
        self.source.chapters.all().delete()
        self.add_chapters(self.source, [300])

        self.assertIsNone(svc.cut_next_part(self.audiobook))
        self.assertEqual(self.ids(svc.cut_next_part(self.audiobook, allow_tail=True)), [1])

        self.source.status = "Completed"
        self.source.last_chapter_update = timezone.now() - timedelta(days=1)
        self.source.save()
        self.assertIsNone(svc.cut_next_part(self.audiobook))

        self.source.last_chapter_update = timezone.now() - timedelta(days=30)
        self.source.save()
        cut = svc.cut_next_part(self.audiobook)
        self.assertEqual(self.ids(cut), [1])
        self.assertTrue(cut["is_tail"])

    def test_next_cut_starts_after_the_previous_part(self):
        first = svc.enqueue_next_part(self.audiobook)
        second = svc.enqueue_next_part(self.audiobook, allow_tail=True)

        self.assertEqual((first.chapter_start, first.chapter_end), (1, 2))
        self.assertEqual((second.chapter_start, second.chapter_end), (3, 6))

    def test_returns_none_when_nothing_is_left(self):
        svc.enqueue_next_part(self.audiobook)
        svc.enqueue_next_part(self.audiobook, allow_tail=True)

        self.assertIsNone(svc.cut_next_part(self.audiobook, allow_tail=True))


    def test_many_chapters_cross_the_batch_boundary(self):
        self.source.chapters.all().delete()
        self.add_chapters(self.source, [1] * 450)

        cut = svc.cut_next_part(self.audiobook, allow_tail=True)

        self.assertEqual(self.ids(cut), list(range(1, 451)))
        self.assertEqual(cut["word_count"], 450)
        self.assertTrue(cut["is_tail"])

    def test_total_equal_to_target_at_the_end_is_full(self):
        self.source.chapters.all().delete()
        self.add_chapters(self.source, [400, 600])

        cut = svc.cut_next_part(self.audiobook)

        self.assertEqual(self.ids(cut), [1, 2])
        self.assertEqual(cut["word_count"], 1000)
        self.assertFalse(cut["is_tail"])

    def test_missing_file_stops_the_cut_and_stays_uncounted(self):
        self.source.chapters.all().delete()
        self.add_chapters(self.source, [400, 300, 200])
        os.remove(os.path.join(self.source.absolute_source_path, "json", "00002.json"))

        self.assertIsNone(svc.cut_next_part(self.audiobook))
        cut = svc.cut_next_part(self.audiobook, allow_tail=True)

        self.assertEqual(self.ids(cut), [1])
        self.assertEqual(cut["word_count"], 400)
        self.assertTrue(cut["is_tail"])
        self.assertIsNone(Chapter.objects.get(novel_from_source=self.source, chapter_id=2).word_count)


@override_settings(AUDIOBOOK_PART_WORDS=1000)
class EnqueueNextPartTests(AudiobookBase):
    def setUp(self):
        super().setUp()
        self.source = self.make_source()
        self.add_chapters(self.source, [400, 400, 300])
        self.audiobook = self.make_audiobook(self.source)

    def test_index_increments(self):
        first = svc.enqueue_next_part(self.audiobook, priority=7)
        second = svc.enqueue_next_part(self.audiobook, allow_tail=True)

        self.assertEqual(first.index, 1)
        self.assertEqual(second.index, 2)
        self.assertEqual(first.priority, 7)
        self.assertEqual(second.priority, 0)

    def test_estimated_duration_and_content_hash(self):
        part = svc.enqueue_next_part(self.audiobook)
        chapters = list(self.source.chapters.filter(chapter_id__in=[1, 2]).order_by("chapter_id"))

        self.assertEqual(part.word_count, 800)
        self.assertAlmostEqual(part.estimated_duration_s, 800 / 155 * 60)
        self.assertEqual(len(part.content_hash), 64)
        self.assertEqual(part.content_hash, svc.content_hash(chapters))
        self.assertEqual(part.chapter_ids, [ch.pk for ch in chapters])

    def test_unreadable_chapter_creates_no_part_and_logs_a_warning(self):
        # Counted earlier, then its file went missing: the cut has no readable body to hash.
        Chapter.objects.filter(novel_from_source=self.source, chapter_id=1).update(word_count=400)
        os.remove(os.path.join(self.source.absolute_source_path, "json", "00001.json"))

        with self.assertLogs("lncrawler_api.audiobooks", level="WARNING"):
            self.assertIsNone(svc.enqueue_next_part(self.audiobook))

        self.assertFalse(AudiobookPart.objects.exists())
        self.audiobook.refresh_from_db()
        self.assertIsNone(self.audiobook.last_enqueued_at)

    def test_returns_none_when_nothing_to_cut(self):
        svc.enqueue_next_part(self.audiobook)

        # The 300-word tail is not cut: the source is still ongoing.
        self.assertIsNone(svc.enqueue_next_part(self.audiobook))
        self.assertEqual(AudiobookPart.objects.count(), 1)

    def test_exclusive_refuses_while_a_part_is_queued(self):
        self.assertIsNotNone(svc.enqueue_next_part(self.audiobook))

        self.assertIsNone(svc.enqueue_next_part(self.audiobook, exclusive=True))
        self.assertEqual(AudiobookPart.objects.count(), 1)

    def test_enqueue_sets_last_enqueued_at(self):
        self.assertIsNone(self.audiobook.last_enqueued_at)

        svc.enqueue_next_part(self.audiobook)

        self.audiobook.refresh_from_db()
        self.assertIsNotNone(self.audiobook.last_enqueued_at)

    def test_word_counts_survive_an_enqueue_that_cuts_nothing(self):
        # A 300-word tail of an ongoing source is not cut, but its count is stored
        self.source.chapters.all().delete()
        self.add_chapters(self.source, [300])

        self.assertIsNone(svc.enqueue_next_part(self.audiobook))
        self.assertEqual(Chapter.objects.get(novel_from_source=self.source, chapter_id=1).word_count, 300)

        with patch.object(svc, "_chapter_body") as read_body:
            self.assertIsNone(svc.enqueue_next_part(self.audiobook))
        read_body.assert_not_called()


class PartOperationTests(AudiobookBase):
    def setUp(self):
        super().setUp()
        self.audiobook = self.make_audiobook(self.make_source())

    def test_delete_audio_files(self):
        audio = svc.audio_dir(self.audiobook.source)
        os.makedirs(audio / "part-001", exist_ok=True)
        (audio / "part-001" / "00001.ogg").write_bytes(b"x" * 10)
        self.audiobook.published = True
        self.audiobook.save()
        part = self.make_part(self.audiobook, status="done", duration_s=100, size_bytes=10)
        Chapter.objects.create(novel_from_source=self.audiobook.source, chapter_id=1, url="http://x/1", title="C1")
        AudiobookChapter.objects.create(
            part=part,
            chapter=Chapter.objects.get(chapter_id=1),
            file_path="foo/site/audio/part-001/00001.ogg",
            duration_s=100,
            size_bytes=10,
            sha256="0" * 64,
        )

        # The folder is removed on commit: run the post-commit callbacks explicitly.
        with self.captureOnCommitCallbacks(execute=True):
            freed = svc.delete_audio_files(self.audiobook)

        self.assertEqual(freed, 10)
        self.assertFalse(audio.exists())
        self.assertFalse(AudiobookChapter.objects.exists())
        part.refresh_from_db()
        self.assertEqual((part.status, part.duration_s, part.size_bytes), ("stale", 0, 0))
        self.audiobook.refresh_from_db()
        self.assertFalse(self.audiobook.published)
        self.assertEqual(self.audiobook.total_size_bytes, 0)
        self.assertEqual(self.audiobook.parts_done, 1)

    def test_retry_part(self):
        part = self.make_part(
            self.audiobook,
            status="failed",
            attempts=3,
            error_message="boom",
            worker_id="w1",
            claimed_at=timezone.now(),
            lease_until=timezone.now(),
        )

        svc.retry_part(part)

        part.refresh_from_db()
        self.assertEqual(part.status, "queued")
        self.assertEqual(part.attempts, 0)
        self.assertEqual(part.error_message, "")
        self.assertEqual(part.worker_id, "")
        self.assertIsNone(part.claimed_at)
        self.assertIsNone(part.lease_until)

    def test_regenerate_part(self):
        part = self.make_part(self.audiobook, status="done", qa_passed=True, approved=True, attempts=2)

        svc.regenerate_part(part)

        part.refresh_from_db()
        self.assertEqual(part.status, "queued")
        self.assertEqual(part.priority, 100)
        self.assertIsNone(part.qa_passed)
        self.assertFalse(part.approved)
        self.assertEqual(part.attempts, 0)


class DeleteAudioFilesSafetyTests(AudiobookBase):
    def setUp(self):
        super().setUp()
        self.source = self.make_source()
        self.audiobook = self.make_audiobook(self.source)
        self.audio = svc.audio_dir(self.source)
        os.makedirs(self.audio / "part-001", exist_ok=True)
        (self.audio / "part-001" / "00001.ogg").write_bytes(b"x" * 10)

    def test_empty_source_path_returns_zero_and_deletes_nothing(self):
        NovelFromSource.objects.filter(pk=self.source.pk).update(source_path="")
        self.audiobook.source.refresh_from_db()

        self.assertEqual(svc.delete_audio_files(self.audiobook), 0)
        self.assertTrue((self.audio / "part-001" / "00001.ogg").exists())

    def test_source_outside_output_path_is_refused(self):
        with self.subTest("source folder outside LNCRAWL_OUTPUT_PATH"), override_settings(
            LNCRAWL_OUTPUT_PATH=os.path.join(self.tmp, "elsewhere")
        ):
            self.assertEqual(svc.delete_audio_files(self.audiobook), 0)
            self.assertTrue(self.audio.exists())

        with self.subTest("source folder equal to LNCRAWL_OUTPUT_PATH"), override_settings(
            LNCRAWL_OUTPUT_PATH=os.path.join(self.tmp, "foo", "site")
        ):
            self.assertEqual(svc.delete_audio_files(self.audiobook), 0)
            self.assertTrue(self.audio.exists())


class FollowSourceTests(AudiobookBase):
    def setUp(self):
        super().setUp()
        self.moved = Novel.objects.create(title="Moved", slug="moved", novel_path="moved")
        self.source = self.make_source()
        self.audiobook = self.make_audiobook(self.source)

    def move_source(self):
        NovelFromSource.objects.filter(pk=self.source.pk).update(novel=self.moved)
        self.source.refresh_from_db()

    def add_audio(self, audiobook, seconds):
        """A done part of ``seconds`` with one audio file on disk. Returns the audio folder."""
        self.make_part(audiobook, index=audiobook.parts.count() + 1, status="done", duration_s=seconds, size_bytes=10)
        audio = svc.audio_dir(audiobook.source)
        os.makedirs(audio, exist_ok=True)
        (audio / "00001.ogg").write_bytes(b"x" * 10)
        audiobook.refresh_totals()
        return audio

    def test_audiobook_moves_with_its_source(self):
        self.move_source()

        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(svc.follow_source(self.source), 1)

        self.audiobook.refresh_from_db()
        self.assertEqual(self.audiobook.novel, self.moved)

    def test_longer_audiobook_is_kept_and_the_other_is_deleted_with_its_files(self):
        other_source = self.make_source("other")
        NovelFromSource.objects.filter(pk=other_source.pk).update(novel=self.moved)
        existing = Audiobook.objects.create(novel=self.moved, source=other_source)
        audio_existing = self.add_audio(existing, 100)
        self.add_audio(self.audiobook, 500)
        self.move_source()

        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(svc.follow_source(self.source), 1)

        self.assertFalse(Audiobook.objects.filter(pk=existing.pk).exists())
        self.assertFalse(audio_existing.exists())
        self.audiobook.refresh_from_db()
        self.assertEqual(self.audiobook.novel, self.moved)

    def test_longer_existing_audiobook_wins_and_the_moving_one_is_deleted(self):
        other_source = self.make_source("other")
        NovelFromSource.objects.filter(pk=other_source.pk).update(novel=self.moved)
        existing = Audiobook.objects.create(novel=self.moved, source=other_source)
        self.add_audio(existing, 500)
        audio_moving = self.add_audio(self.audiobook, 100)
        self.move_source()

        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(svc.follow_source(self.source), 0)

        self.assertFalse(Audiobook.objects.filter(pk=self.audiobook.pk).exists())
        self.assertFalse(audio_moving.exists())
        self.assertTrue(Audiobook.objects.filter(pk=existing.pk).exists())

    def test_audio_of_the_deleted_loser_stays_when_the_transaction_rolls_back(self):
        other_source = self.make_source("other")
        NovelFromSource.objects.filter(pk=other_source.pk).update(novel=self.moved)
        existing = Audiobook.objects.create(novel=self.moved, source=other_source)
        audio_existing = self.add_audio(existing, 100)
        self.add_audio(self.audiobook, 500)
        self.move_source()

        # The loser (the shorter book) is deleted inside a transaction that then fails.
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    svc.follow_source(self.source)
                    raise RuntimeError("the surrounding change fails")

        self.assertTrue(Audiobook.objects.filter(pk=existing.pk).exists())
        self.assertTrue(audio_existing.exists())

    def test_move_source_to_novel_carries_the_audiobook(self):
        move_source_to_novel(self.source, self.moved, move_files=False)

        self.audiobook.refresh_from_db()
        self.assertEqual(self.audiobook.novel, self.moved)

    def test_move_source_to_novel_with_files_carries_the_audiobook_and_its_audio(self):
        self.add_audio(self.audiobook, 100)

        with self.captureOnCommitCallbacks(execute=True):
            with file_journal() as files:
                move_source_to_novel(self.source, self.moved, move_files=True, files=files)

        self.audiobook.refresh_from_db()
        self.source.refresh_from_db()
        self.assertEqual(self.audiobook.novel, self.moved)
        self.assertTrue(svc.audio_dir(self.source).joinpath("00001.ogg").is_file())


class SourceDeletionTests(AudiobookBase):
    def test_deleting_a_source_cascades_to_its_audiobook(self):
        source = self.make_source()
        audiobook = self.make_audiobook(source)

        source.delete()

        self.assertFalse(Audiobook.objects.filter(pk=audiobook.pk).exists())


class AudiobookAdminTests(AudiobookBase):
    def setUp(self):
        super().setUp()
        self.admin_user = get_user_model().objects.create_superuser("audio-admin", "audio@example.com", "pw")
        self.client.force_login(self.admin_user)
        self.source = self.make_source()
        self.add_chapters(self.source, [400, 400, 300])
        self.audiobook = self.make_audiobook(self.source)

    def test_changelist_and_dashboard(self):
        AudiobookWorker.objects.create(worker_id="w1", last_seen_at=timezone.now())
        part = self.make_part(self.audiobook, status="done", completed_at=timezone.now(), duration_s=3600)

        changelist = self.client.get(reverse("admin:lncrawler_api_audiobook_changelist"))
        dashboard = self.client.get(reverse("admin:lncrawler_api_audiobook_dashboard"))
        part_page = self.client.get(reverse("admin:lncrawler_api_audiobookpart_change", args=[part.pk]))

        self.assertEqual(changelist.status_code, 200)
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(part_page.status_code, 200)

    def test_generate_audiobook_action_on_novel(self):
        url = reverse("admin:lncrawler_api_novel_changelist")

        response = self.client.post(url, {"action": "generate_audiobook", "_selected_action": [self.novel.pk]})

        self.assertEqual(response.status_code, 302)
        audiobook = Audiobook.objects.get(novel=self.novel)
        part = audiobook.parts.get()
        self.assertEqual(part.index, 1)
        self.assertEqual(part.priority, 100)

    @override_settings(AUDIOBOOK_PART_WORDS=500)
    def test_enqueue_next_is_not_exclusive(self):
        url = reverse("admin:lncrawler_api_audiobook_changelist")
        selected = {"action": "enqueue_next", "_selected_action": [self.audiobook.pk]}

        self.client.post(url, selected)
        self.client.post(url, selected)

        self.assertEqual(self.audiobook.parts.filter(status="queued").count(), 2)
        self.audiobook.refresh_from_db()
        self.assertIsNotNone(self.audiobook.last_enqueued_at)

    def test_enqueue_skips_dmca_and_inactive_audiobooks(self):
        self.novel.is_dmca = True
        self.novel.save()
        url = reverse("admin:lncrawler_api_audiobook_changelist")
        selected = {"action": "enqueue_next", "_selected_action": [self.audiobook.pk]}

        self.client.post(url, selected)
        self.assertFalse(self.audiobook.parts.exists())

        self.novel.is_dmca = False
        self.novel.save()
        self.audiobook.status = "paused"
        self.audiobook.save()
        self.client.post(url, selected)
        self.assertFalse(self.audiobook.parts.exists())

    def test_mark_dmca_leaves_existing_audiobooks_alone(self):
        self.audiobook.published = True
        self.audiobook.save()

        self.client.post(
            reverse("admin:lncrawler_api_novel_changelist"),
            {"action": "mark_dmca", "_selected_action": [self.novel.pk]},
        )

        self.novel.refresh_from_db()
        self.audiobook.refresh_from_db()
        self.assertTrue(self.novel.is_dmca)
        self.assertTrue(self.audiobook.published)
        self.assertEqual(self.audiobook.status, "active")

    def test_delete_audio_files_confirmation_page_and_apply(self):
        url = reverse("admin:lncrawler_api_audiobook_changelist")
        audio = svc.audio_dir(self.source)
        os.makedirs(audio, exist_ok=True)
        (audio / "00001.ogg").write_bytes(b"x" * 10)
        selected = {"action": "delete_audio_files", "_selected_action": [self.audiobook.pk]}

        page = self.client.post(url, selected)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Confirm: delete audio files")
        self.assertTrue(audio.exists())

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, {**selected, "apply": "Confirm"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(audio.exists())
