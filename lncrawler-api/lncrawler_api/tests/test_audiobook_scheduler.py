"""Audiobooks phase 2: the scheduled enqueue, the lease reaper, and the housekeeping."""

import json
import os
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from ..models import (
    Audiobook,
    AudiobookPart,
    AudiobookWorker,
    Chapter,
    ExternalSource,
    Novel,
    NovelFromSource,
    ScheduledTask,
)
from ..services import audiobook_scheduler as sched
from ..services import audiobook_service as svc
from .helpers import MergeTestCase
from .test_audiobooks import body_of

GB = 1024 ** 3

ENABLED = dict(
    AUDIOBOOK_ENABLED=True,
    AUDIOBOOK_PART_WORDS=100,
    AUDIOBOOK_QUEUE_WORDS=1_000_000,
    AUDIOBOOK_DISK_BUDGET_GB=50,
)


@override_settings(**ENABLED)
class SchedulerBase(MergeTestCase):
    """Novels with English sources under the test output path. One worker announcing English is set up, so new
    books can start; the popularity of a novel in a language is the total views of its sources in it."""

    def setUp(self):
        super().setUp()
        AudiobookWorker.objects.create(worker_id='announcer', last_seen_at=timezone.now(), languages=['en'])

    def make_book(self, slug, words, views=0, dmca=False, language='en', status='Ongoing',
                  last_update=None, write_files=True, first_id=1):
        novel = Novel.objects.create(title=slug, slug=slug, novel_path=slug, is_dmca=dmca)
        source_path = os.path.join(slug, 'site')
        os.makedirs(os.path.join(self.tmp, source_path), exist_ok=True)
        source = NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name=f"site-{slug}"),
            title=slug,
            source_url=f"http://{slug}/1",
            source_path=source_path,
            source_slug='site',
            language=language,
            status=status,
            last_chapter_update=last_update,
            total_views=views,
        )
        self.add_chapters(source, words, first_id=first_id, write_files=write_files)
        return novel, source

    def add_chapters(self, source, words, first_id=1, write_files=True):
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
                has_content=True,
            )

    def start_book(self, slug, words, views=0):
        """A novel whose audiobook has one done part, so the enqueue has something to continue."""
        novel, source = self.make_book(slug, words, views=views)
        audiobook = Audiobook.objects.create(novel=novel, source=source)
        first = svc.enqueue_next_part(audiobook)
        first.status = 'done'
        first.completed_at = timezone.now() - timedelta(days=2)
        first.save()
        return audiobook

    def set_times(self, audiobook, created, enqueued):
        """Set when a book was created and last served, to fix its place in the round-robin order."""
        Audiobook.objects.filter(pk=audiobook.pk).update(created_at=created, last_enqueued_at=enqueued)

    def parts_of(self, novel):
        return AudiobookPart.objects.filter(audiobook__novel=novel)


class DisabledTests(SchedulerBase):
    @override_settings(AUDIOBOOK_ENABLED=False)
    def test_enqueue_is_skipped_and_upkeep_still_runs(self):
        novel, source = self.make_book('off', [60, 60, 60, 60])
        audiobook = Audiobook.objects.create(novel=novel, source=source)
        part = AudiobookPart.objects.create(
            audiobook=audiobook, index=1, chapter_start=1, chapter_end=1, word_count=60,
            status='claimed', lease_until=timezone.now() - timedelta(minutes=1),
        )

        self.assertEqual(sched.enqueue_audiobooks(), {'skipped': 'disabled'})
        self.assertEqual(AudiobookPart.objects.count(), 1)

        # Published audiobooks stay live while generation is off, so their upkeep goes on
        self.assertNotIn('skipped', sched.reap_expired_leases())
        part.refresh_from_db()
        self.assertEqual(part.status, 'queued')
        self.assertNotIn('skipped', sched.audiobook_housekeeping())


class EnqueueTests(SchedulerBase):
    def test_longest_waiting_started_book_goes_first(self):
        older = self.start_book('older', [60] * 12)
        newer = self.start_book('newer', [60] * 12)
        now = timezone.now()
        self.set_times(older, created=now - timedelta(days=9), enqueued=now - timedelta(days=4))
        self.set_times(newer, created=now - timedelta(days=9), enqueued=now - timedelta(days=1))

        with override_settings(AUDIOBOOK_QUEUE_WORDS=60):
            summary = sched.enqueue_audiobooks()

        self.assertEqual(summary['started_parts'], 1)
        self.assertEqual(older.parts.filter(status='queued', priority=0).count(), 1)
        self.assertEqual(newer.parts.filter(status='queued').count(), 0)

    def test_new_book_goes_first_when_it_has_waited_longer(self):
        started = self.start_book('served', [60] * 12)
        now = timezone.now()
        self.set_times(started, created=now - timedelta(days=1), enqueued=now - timedelta(hours=1))
        self.make_book('fresh', [60] * 12, views=5)

        with override_settings(AUDIOBOOK_QUEUE_WORDS=60):
            summary = sched.enqueue_audiobooks()

        self.assertEqual(summary['new_books'], 1)
        self.assertEqual(summary['started_parts'], 0)
        self.assertEqual(started.parts.filter(status='queued').count(), 0)
        self.assertTrue(Audiobook.objects.filter(novel__slug='fresh').exists())

    def test_tie_goes_to_the_more_popular_book_and_not_to_the_new_slot(self):
        when = timezone.now() - timedelta(days=1)
        popular = self.start_book('popular', [60] * 12, views=50)
        quiet = self.start_book('quiet', [60] * 12, views=1)
        self.set_times(popular, created=when, enqueued=when)
        self.set_times(quiet, created=when, enqueued=when)
        self.make_book('fresh', [60] * 12, views=99)

        with override_settings(AUDIOBOOK_QUEUE_WORDS=60):
            summary = sched.enqueue_audiobooks()

        self.assertEqual(summary['started_parts'], 1)
        self.assertEqual(summary['new_books'], 0)
        self.assertEqual(popular.parts.filter(status='queued').count(), 1)
        self.assertEqual(quiet.parts.filter(status='queued').count(), 0)
        self.assertFalse(Audiobook.objects.filter(novel__slug='fresh').exists())

    def test_huge_novel_gets_one_part_per_run(self):
        book = self.start_book('huge', [60] * 12)

        for run in range(1, 6):
            sched.enqueue_audiobooks()
            self.assertEqual(book.parts.count(), 1 + run)
            book.parts.filter(status='queued').update(status='done')

        sched.enqueue_audiobooks()
        sched.enqueue_audiobooks()
        self.assertEqual(book.parts.filter(status='queued').count(), 1)

    def test_books_with_a_queued_part_are_skipped(self):
        busy = self.start_book('busy', [60] * 12)
        svc.enqueue_next_part(busy)
        idle = self.start_book('idle', [60] * 12)

        summary = sched.enqueue_audiobooks()

        self.assertEqual(busy.parts.filter(status='queued').count(), 1)
        self.assertEqual(idle.parts.filter(status='queued').count(), 1)
        self.assertEqual(summary['started_parts'], 1)

    def test_book_that_cannot_cut_a_part_is_skipped(self):
        stuck = self.start_book('stuck', [60, 60, 30])
        ready = self.start_book('ready', [60] * 12)
        now = timezone.now()
        self.set_times(stuck, created=now - timedelta(days=9), enqueued=now - timedelta(days=4))
        self.set_times(ready, created=now - timedelta(days=9), enqueued=now - timedelta(days=1))

        summary = sched.enqueue_audiobooks()

        self.assertEqual(stuck.parts.count(), 1)
        self.assertEqual(ready.parts.filter(status='queued').count(), 1)
        self.assertEqual(summary['started_parts'], 1)

    def test_budget_stops_the_run_between_books(self):
        now = timezone.now()
        books = [self.start_book(f'budget-{index}', [60] * 12) for index in range(3)]
        for offset, book in enumerate(books):
            self.set_times(book, created=now - timedelta(days=9), enqueued=now - timedelta(days=5 - offset))

        with override_settings(AUDIOBOOK_QUEUE_WORDS=120):
            summary = sched.enqueue_audiobooks()

        self.assertEqual(summary['started_parts'], 2)
        self.assertEqual(summary['stopped'], 'queue_full')
        self.assertEqual(books[0].parts.get(status='queued').priority, 0)
        self.assertEqual(books[2].parts.filter(status='queued').count(), 0)

    def test_queue_words_count_queued_and_claimed_parts(self):
        novel, source = self.make_book('claimed', [60] * 6)
        audiobook = Audiobook.objects.create(novel=novel, source=source)
        AudiobookPart.objects.create(
            audiobook=audiobook, index=1, chapter_start=1, chapter_end=1, word_count=60,
            status='claimed', lease_until=timezone.now() + timedelta(minutes=10),
        )
        other = self.start_book('other', [60] * 12)

        with override_settings(AUDIOBOOK_QUEUE_WORDS=100):
            summary = sched.enqueue_audiobooks()

        self.assertEqual(other.parts.filter(status='queued').count(), 1)
        self.assertEqual(summary['queued_words'], 120)
        self.assertEqual(summary['stopped'], 'queue_full')

    def test_disk_budget_stops_the_run(self):
        audiobook = self.start_book('full-disk', [60, 60, 60, 60])
        Audiobook.objects.filter(pk=audiobook.pk).update(total_size_bytes=2 * GB)
        self.make_book('waiting', [60, 60, 60, 60])

        with override_settings(AUDIOBOOK_DISK_BUDGET_GB=1), self.assertLogs('lncrawler_api.audiobooks', 'WARNING'):
            summary = sched.enqueue_audiobooks()

        self.assertEqual(summary['stopped'], 'disk_budget')
        self.assertEqual(summary['started_parts'], 0)
        self.assertEqual(summary['new_books'], 0)
        self.assertEqual(audiobook.parts.filter(status='queued').count(), 0)
        self.assertFalse(Audiobook.objects.filter(novel__slug='waiting').exists())

    def test_new_books_follow_rank_order(self):
        self.make_book('low', [60] * 4, views=5)
        self.make_book('high', [60] * 4, views=50)
        self.make_book('middle', [60] * 4, views=10)
        self.make_book('lowest', [60] * 4, views=1)

        with override_settings(AUDIOBOOK_QUEUE_WORDS=120):
            summary = sched.enqueue_audiobooks()

        self.assertEqual(summary['new_books'], 2)
        started = set(Audiobook.objects.values_list('novel__slug', flat=True))
        self.assertEqual(started, {'high', 'middle'})

    def add_source(self, novel, words, language, views):
        """Another source of an existing novel, in another language."""
        source_path = os.path.join(novel.slug, language)
        os.makedirs(os.path.join(self.tmp, source_path), exist_ok=True)
        source = NovelFromSource.objects.create(
            novel=novel,
            external_source=ExternalSource.objects.create(source_name=f"site-{novel.slug}-{language}"),
            title=novel.title,
            source_url=f"http://{novel.slug}/{language}",
            source_path=source_path,
            source_slug=language,
            language=language,
            status='Ongoing',
            total_views=views,
        )
        self.add_chapters(source, words)
        return source

    def test_each_language_ranks_on_its_own_popularity(self):
        self.worker_languages(['en', 'fr'])
        lotm, _ = self.make_book('lotm', [60] * 4, views=500_000)
        self.add_source(lotm, [60] * 4, 'fr', 300_000)
        self.make_book('martial', [60] * 4, views=600_000)
        self.make_book('other', [60] * 4, views=150_000)
        self.add_source(lotm, [60] * 4, 'de', 990_000)

        with override_settings(AUDIOBOOK_QUEUE_WORDS=180):
            summary = sched.enqueue_audiobooks()

        self.assertEqual(summary['new_books'], 3)
        started = list(Audiobook.objects.order_by('created_at').values_list('novel__slug', 'language'))
        self.assertEqual(started, [('martial', 'en'), ('lotm', 'en'), ('lotm', 'fr')])

    def test_only_announced_languages_start_new_books(self):
        self.make_book('english', [60] * 4, views=10)
        novel, _ = self.make_book('french', [60] * 4, views=1_000_000, language='fr')
        self.add_source(novel, [60] * 4, 'de', 1_000_000)

        sched.enqueue_audiobooks()

        self.assertEqual(set(Audiobook.objects.values_list('language', flat=True)), {'en'})

    def test_no_announcing_worker_means_no_new_books(self):
        AudiobookWorker.objects.all().delete()
        self.make_book('fresh', [60] * 4, views=10)

        summary = sched.enqueue_audiobooks()

        self.assertEqual(summary['new_books'], 0)
        self.assertFalse(Audiobook.objects.exists())

    def test_started_book_in_an_unannounced_language_gets_no_part(self):
        novel, source = self.make_book('french', [60] * 12, language='fr')
        audiobook = Audiobook.objects.create(novel=novel, source=source, language='fr')
        first = svc.enqueue_next_part(audiobook)
        first.status = 'done'
        first.completed_at = timezone.now() - timedelta(days=2)
        first.save()

        summary = sched.enqueue_audiobooks()

        self.assertEqual(summary['started_parts'], 0)
        self.assertEqual(self.parts_of(novel).count(), 1)

    def test_new_book_that_gets_no_part_keeps_its_word_counts(self):
        # Two short chapters of an ongoing source: nothing can be cut, so the new book is rolled back
        novel, source = self.make_book('short', [30, 30], views=10)

        sched.enqueue_audiobooks()

        self.assertFalse(Audiobook.objects.exists())
        self.assertFalse(Chapter.objects.filter(novel_from_source=source, word_count__isnull=True).exists())

    def test_pair_with_an_audiobook_is_skipped_while_the_other_language_starts(self):
        self.worker_languages(['en', 'fr'])
        novel, english = self.make_book('split', [60] * 4, views=900_000)
        french = self.add_source(novel, [60] * 4, 'fr', 100_000)
        Audiobook.objects.create(novel=novel, source=english, language='en')

        sched.enqueue_audiobooks()

        self.assertFalse(Audiobook.objects.filter(novel=novel, language='en', parts__isnull=False).exists())
        self.assertTrue(Audiobook.objects.filter(novel=novel, language='fr', source=french).exists())

    def worker_languages(self, languages):
        AudiobookWorker.objects.update(languages=languages)

    def test_new_books_get_only_one_part_per_run(self):
        self.make_book('one', [60] * 6, views=1)

        sched.enqueue_audiobooks()

        self.assertEqual(AudiobookPart.objects.filter(audiobook__novel__slug='one').count(), 1)

    def test_new_book_scan_gives_up_after_the_novel_limit(self):
        self.make_book('short-a', [20, 20], views=40)
        self.make_book('short-b', [20, 20], views=30)
        self.make_book('short-c', [20, 20], views=20)
        self.make_book('good', [60] * 4, views=1)

        with patch.object(sched, 'NEW_BOOK_NOVEL_LIMIT', 2):
            summary = sched.enqueue_audiobooks()

        self.assertEqual(summary['new_books'], 0)
        self.assertFalse(Audiobook.objects.filter(novel__slug='good').exists())

    def test_new_book_scan_gives_up_after_the_read_limit(self):
        self.make_book('first', [60] * 4, views=40)
        self.make_book('good', [60] * 4, views=1)

        # 'first' reads its 4 chapter files, which passes the limit of 2: the scan stops there.
        with patch.object(sched, 'NEW_BOOK_READ_LIMIT', 2):
            summary = sched.enqueue_audiobooks()

        self.assertEqual(summary['new_books'], 1)
        self.assertTrue(Audiobook.objects.filter(novel__slug='first').exists())
        self.assertFalse(Audiobook.objects.filter(novel__slug='good').exists())

    def test_counted_short_novels_do_not_stop_the_scan_before_a_later_one(self):
        for index in range(3):
            _, source = self.make_book(f'short-{index}', [20, 20], views=40 - index)
            Chapter.objects.filter(novel_from_source=source).update(word_count=20)
        self.make_book('good', [60] * 4, views=1)

        # Three counted short novels rank above 'good' and cost only a query each, so 'good' is reached.
        with patch.object(sched, 'NEW_BOOK_NOVEL_LIMIT', 5):
            summary = sched.enqueue_audiobooks()

        self.assertEqual(summary['new_books'], 1)
        self.assertTrue(Audiobook.objects.filter(novel__slug='good').exists())

    def test_clash_on_one_novel_is_logged_and_the_run_goes_on(self):
        self.make_book('clash', [60] * 4, views=40)
        self.make_book('good', [60] * 4, views=1)
        real = svc.get_or_create_audiobook

        def clash(novel, language='en', source=None):
            if novel.slug == 'clash':
                raise IntegrityError('duplicate key')
            return real(novel, language, source=source)

        with patch.object(svc, 'get_or_create_audiobook', side_effect=clash), \
                self.assertLogs('lncrawler_api.audiobooks', 'WARNING'):
            summary = sched.enqueue_audiobooks()

        self.assertEqual(summary['new_books'], 1)
        self.assertEqual(set(Audiobook.objects.values_list('novel__slug', flat=True)), {'good'})

    def test_dmca_non_english_and_short_novels_are_skipped(self):
        self.make_book('dmca', [60] * 4, views=40, dmca=True)
        self.make_book('japanese', [60] * 4, views=30, language='ja')
        self.make_book('short', [20, 20], views=20)
        self.make_book('good', [60] * 4, views=1)

        sched.enqueue_audiobooks()

        self.assertEqual(set(Audiobook.objects.values_list('novel__slug', flat=True)), {'good'})

    def test_novel_with_too_few_words_for_a_full_part_leaves_no_row(self):
        # 60 words, but a tail is not cut for a source that is still ongoing
        self.make_book('tail', [30, 30], views=1)

        summary = sched.enqueue_audiobooks()

        self.assertEqual(summary['new_books'], 0)
        self.assertFalse(Audiobook.objects.filter(novel__slug='tail').exists())

    def test_paused_and_retired_audiobooks_are_untouched(self):
        for slug, status in (('paused', 'paused'), ('retired', 'retired')):
            novel, source = self.make_book(slug, [60] * 4, views=10)
            Audiobook.objects.create(novel=novel, source=source, status=status)

        sched.enqueue_audiobooks()

        self.assertFalse(AudiobookPart.objects.filter(audiobook__novel__slug__in=['paused', 'retired']).exists())
        self.assertEqual(Audiobook.objects.get(novel__slug='paused').status, 'paused')
        self.assertEqual(Audiobook.objects.get(novel__slug='retired').status, 'retired')


class RotationShareTests(SchedulerBase):
    def new_books_started(self, prefix, started_count, runs=10):
        """New books started over ``runs`` runs that each have room for one part, with ``started_count``
        books already in rotation. The workers finish every queued part between two runs."""
        now = timezone.now()
        for index in range(started_count):
            book = self.start_book(f'{prefix}-started-{index}', [60] * 12)
            self.set_times(book, created=now - timedelta(days=10), enqueued=now - timedelta(days=5 - index))
        for index in range(runs):
            self.make_book(f'{prefix}-fresh-{index}', [60] * 12, views=100 - index)
        for _ in range(runs):
            with override_settings(AUDIOBOOK_QUEUE_WORDS=60):
                sched.enqueue_audiobooks()
            AudiobookPart.objects.filter(status='queued').update(status='done')
        return Audiobook.objects.filter(novel__slug__startswith=f'{prefix}-fresh').count()

    def test_new_slot_and_started_book_alternate(self):
        started = self.start_book('alt-started', [60] * 12)
        now = timezone.now()
        # The new slot's newest audiobook is older than the started book's last part, so the slot goes first.
        self.set_times(started, created=now - timedelta(days=10), enqueued=now - timedelta(days=5))
        self.make_book('alt-new-a', [60] * 12, views=20)
        self.make_book('alt-new-b', [60] * 12, views=10)

        sched.enqueue_audiobooks()

        order = AudiobookPart.objects.filter(status='queued').order_by('created_at').values_list('audiobook__novel__slug', flat=True)
        self.assertEqual(list(order), ['alt-new-a', 'alt-started', 'alt-new-b'])

    def test_more_books_in_rotation_mean_fewer_new_books(self):
        alone = self.new_books_started('one', 1)
        Audiobook.objects.all().delete()
        Novel.objects.all().delete()

        crowded = self.new_books_started('four', 4)

        self.assertEqual((alone, crowded), (4, 2))


class ReapLeaseTests(SchedulerBase):
    def make_claim(self, audiobook, index, lease_offset, attempts=0):
        return AudiobookPart.objects.create(
            audiobook=audiobook, index=index, chapter_start=index, chapter_end=index, word_count=60,
            status='claimed', worker_id='worker-1', attempts=attempts,
            claimed_at=timezone.now() - timedelta(minutes=20), lease_until=timezone.now() + lease_offset,
            progress=0.5, stage='synth',
        )

    def test_expired_claim_is_requeued_with_the_claim_cleared(self):
        novel, source = self.make_book('reap', [60] * 4)
        audiobook = Audiobook.objects.create(novel=novel, source=source)
        part = self.make_claim(audiobook, 1, timedelta(minutes=-1))

        self.assertEqual(sched.reap_expired_leases(), {'requeued': 1, 'failed': 0})

        part.refresh_from_db()
        self.assertEqual(part.status, 'queued')
        self.assertEqual(part.attempts, 1)
        self.assertEqual(part.worker_id, '')
        self.assertIsNone(part.claimed_at)
        self.assertIsNone(part.lease_until)
        self.assertEqual(part.progress, 0)
        self.assertEqual(part.stage, '')

    def test_expired_claim_at_max_attempts_is_failed(self):
        novel, source = self.make_book('exhausted', [60] * 4)
        audiobook = Audiobook.objects.create(novel=novel, source=source)
        part = self.make_claim(audiobook, 1, timedelta(minutes=-1), attempts=2)

        self.assertEqual(sched.reap_expired_leases(), {'requeued': 0, 'failed': 1})

        part.refresh_from_db()
        self.assertEqual(part.status, 'failed')
        self.assertEqual(part.attempts, 3)
        self.assertEqual(part.error_message, 'Lease expired: the worker stopped responding')

    def test_unexpired_and_non_claimed_parts_are_untouched(self):
        novel, source = self.make_book('fresh', [60] * 4)
        audiobook = Audiobook.objects.create(novel=novel, source=source)
        live = self.make_claim(audiobook, 1, timedelta(minutes=10))
        queued = AudiobookPart.objects.create(
            audiobook=audiobook, index=2, chapter_start=2, chapter_end=2, word_count=60,
            status='queued', lease_until=timezone.now() - timedelta(minutes=5),
        )

        self.assertEqual(sched.reap_expired_leases(), {'requeued': 0, 'failed': 0})

        live.refresh_from_db()
        queued.refresh_from_db()
        self.assertEqual((live.status, live.attempts, live.worker_id), ('claimed', 0, 'worker-1'))
        self.assertEqual((queued.status, queued.attempts), ('queued', 0))


class HousekeepingTests(SchedulerBase):
    def test_moved_source_audiobook_follows_the_source(self):
        novel_a, source_a = self.make_book('before', [60] * 4)
        novel_b = Novel.objects.create(title='after', slug='after', novel_path='after')
        audiobook = Audiobook.objects.create(novel=novel_a, source=source_a)
        NovelFromSource.objects.filter(pk=source_a.pk).update(novel=novel_b)

        summary = sched.audiobook_housekeeping()

        self.assertEqual(summary['followed'], 1)
        audiobook.refresh_from_db()
        self.assertEqual(audiobook.novel, novel_b)

    def make_done_part(self, slug, completed, last_update):
        novel, source = self.make_book(slug, [60, 60, 60], last_update=last_update)
        audiobook = Audiobook.objects.create(novel=novel, source=source)
        part = svc.enqueue_next_part(audiobook)
        part.status = 'done'
        part.completed_at = completed
        part.save()
        return source, part

    @override_settings(AUDIOBOOK_PART_WORDS=1000)
    def test_zero_word_chapter_inside_a_part_keeps_it_done(self):
        now = timezone.now()
        novel, source = self.make_book('empty-middle', [60, 0, 60], last_update=now - timedelta(days=1))
        audiobook = Audiobook.objects.create(novel=novel, source=source)
        part = svc.enqueue_next_part(audiobook, allow_tail=True)
        part.status = 'done'
        part.completed_at = now - timedelta(days=2)
        part.save()
        self.assertEqual((part.chapter_start, part.chapter_end), (1, 3))

        summary = sched.audiobook_housekeeping()

        self.assertEqual(summary['stale'], 0)
        part.refresh_from_db()
        self.assertEqual(part.status, 'done')

    def test_changed_text_after_reimport_marks_the_part_stale(self):
        now = timezone.now()
        source, part = self.make_done_part('stale', now - timedelta(days=2), now - timedelta(days=1))
        json_path = os.path.join(source.absolute_source_path, 'json', '00001.json')
        with open(json_path, 'w', encoding='utf-8') as handle:
            json.dump({'title': 'Chapter 1', 'body': body_of(61)}, handle)

        summary = sched.audiobook_housekeeping()

        self.assertEqual(summary['stale'], 1)
        part.refresh_from_db()
        self.assertEqual(part.status, 'stale')
        self.assertIsNotNone(part.checked_at)

    def test_deleted_chapter_marks_the_part_stale_and_is_checked(self):
        now = timezone.now()
        source, part = self.make_done_part('deleted', now - timedelta(days=2), now - timedelta(days=1))
        Chapter.objects.filter(pk=part.chapter_ids[0]).delete()

        summary = sched.audiobook_housekeeping()

        self.assertEqual(summary['stale'], 1)
        part.refresh_from_db()
        self.assertEqual(part.status, 'stale')
        self.assertIsNotNone(part.checked_at)

    def test_unchanged_text_after_reimport_stays_done_and_is_checked(self):
        now = timezone.now()
        source, part = self.make_done_part('same', now - timedelta(days=2), now - timedelta(days=1))

        summary = sched.audiobook_housekeeping()

        self.assertEqual(summary['stale'], 0)
        part.refresh_from_db()
        self.assertEqual(part.status, 'done')
        self.assertIsNotNone(part.checked_at)

    def test_source_not_reimported_since_completion_is_not_read(self):
        now = timezone.now()
        source, part = self.make_done_part('settled', now - timedelta(days=1), now - timedelta(days=3))

        with patch('lncrawler_api.services.audiobook_service.content_hash') as content_hash:
            summary = sched.audiobook_housekeeping()

        content_hash.assert_not_called()
        self.assertEqual(summary['stale'], 0)
        part.refresh_from_db()
        self.assertEqual(part.status, 'done')

    def test_part_checked_before_the_last_update_is_read_again(self):
        now = timezone.now()
        source, part = self.make_done_part('recheck', now - timedelta(days=2), now - timedelta(days=1))
        part.checked_at = now - timedelta(days=3)
        part.save()

        with patch(
            'lncrawler_api.services.audiobook_service.content_hash', wraps=svc.content_hash,
        ) as content_hash:
            sched.audiobook_housekeeping()

        content_hash.assert_called()

    def test_part_checked_after_the_last_update_is_not_read_again(self):
        now = timezone.now()
        source, part = self.make_done_part('checked', now - timedelta(days=2), now - timedelta(days=1))
        part.checked_at = now - timedelta(hours=1)
        part.save()

        with patch('lncrawler_api.services.audiobook_service.content_hash') as content_hash:
            sched.audiobook_housekeeping()

        content_hash.assert_not_called()

    def test_unreadable_chapter_leaves_the_part_done_and_unchecked(self):
        now = timezone.now()
        source, part = self.make_done_part('missing', now - timedelta(days=2), now - timedelta(days=1))
        os.remove(os.path.join(source.absolute_source_path, 'json', '00001.json'))

        summary = sched.audiobook_housekeeping()

        self.assertEqual(summary['stale'], 0)
        part.refresh_from_db()
        self.assertEqual(part.status, 'done')
        self.assertIsNone(part.checked_at)


class DashboardTests(SchedulerBase):
    def test_dashboard_renders_with_the_new_fields(self):
        admin_user = get_user_model().objects.create_superuser("sched-admin", "sched@example.com", "pw")
        self.client.force_login(admin_user)
        ScheduledTask.objects.create(
            name='enqueue_audiobooks', interval_seconds=3600, next_run_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.get(reverse("admin:lncrawler_api_audiobook_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'enqueue_audiobooks')
        self.assertContains(response, 'Queue words (queued and claimed)')
        self.assertContains(response, 'Started books in rotation')
        self.assertEqual(response.context['queue_target_words'], 1_000_000)
