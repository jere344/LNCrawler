"""Audiobooks phase 2: the part cut when a worker claims with nothing queued, and the housekeeping."""

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
WORKER = 'w1'  # the worker that claims in these tests

ENABLED = dict(
    AUDIOBOOK_ENABLED=True,
    AUDIOBOOK_PART_WORDS=100,
    AUDIOBOOK_DISK_BUDGET_GB=50,
)


@override_settings(**ENABLED)
class SchedulerBase(MergeTestCase):
    """Novels with English sources under the test output path. The popularity of a novel in a language is the total
    views of its sources in it."""

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
        """A novel whose audiobook has one done part, so the next claim has something to continue."""
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

    def cut(self, languages=('en',), worker_id=WORKER):
        """One claim with nothing queued: the part cut for it, or None."""
        return sched.cut_work(worker_id, list(languages))

    def serve(self):
        """One claim with nothing queued, and its part done: the slug of the novel the part was cut for."""
        part = self.cut()
        AudiobookPart.objects.filter(pk=part.pk).update(status='done', completed_at=timezone.now())
        return part.audiobook.novel.slug


class DisabledTests(SchedulerBase):
    @override_settings(AUDIOBOOK_ENABLED=False)
    def test_housekeeping_still_follows_moved_sources(self):
        # Published audiobooks stay live while claims are off, so their upkeep goes on
        novel_a, source_a = self.make_book('before', [60] * 4)
        novel_b = Novel.objects.create(title='after', slug='after', novel_path='after')
        audiobook = Audiobook.objects.create(novel=novel_a, source=source_a)
        NovelFromSource.objects.filter(pk=source_a.pk).update(novel=novel_b)

        summary = sched.audiobook_housekeeping()

        self.assertEqual(summary['followed'], 1)
        audiobook.refresh_from_db()
        self.assertEqual(audiobook.novel, novel_b)


class CutWorkTests(SchedulerBase):
    def test_longest_waiting_started_book_goes_first(self):
        older = self.start_book('older', [60] * 12)
        newer = self.start_book('newer', [60] * 12)
        now = timezone.now()
        self.set_times(older, created=now - timedelta(days=9), enqueued=now - timedelta(days=4))
        self.set_times(newer, created=now - timedelta(days=9), enqueued=now - timedelta(days=1))

        part = self.cut()

        self.assertEqual(part.audiobook, older)
        self.assertEqual(part.priority, 0)
        self.assertEqual(newer.parts.filter(status='queued').count(), 0)

    def test_new_book_goes_first_when_it_has_waited_longer(self):
        started = self.start_book('served', [60] * 12)
        now = timezone.now()
        self.set_times(started, created=now - timedelta(days=1), enqueued=now - timedelta(hours=1))
        self.make_book('fresh', [60] * 12, views=5)

        part = self.cut()

        self.assertEqual(part.audiobook.novel.slug, 'fresh')
        self.assertEqual(started.parts.filter(status='queued').count(), 0)

    def test_tie_goes_to_the_more_popular_book_and_not_to_the_new_slot(self):
        when = timezone.now() - timedelta(days=1)
        popular = self.start_book('popular', [60] * 12, views=50)
        quiet = self.start_book('quiet', [60] * 12, views=1)
        self.set_times(popular, created=when, enqueued=when)
        self.set_times(quiet, created=when, enqueued=when)
        self.make_book('fresh', [60] * 12, views=99)

        part = self.cut()

        self.assertEqual(part.audiobook, popular)
        self.assertEqual(quiet.parts.filter(status='queued').count(), 0)
        self.assertFalse(Audiobook.objects.filter(novel__slug='fresh').exists())

    def test_huge_novel_gets_one_part_per_claim(self):
        book = self.start_book('huge', [60] * 12)

        for claim in range(1, 6):
            self.assertIsNotNone(self.cut())
            self.assertEqual(book.parts.count(), 1 + claim)
            book.parts.filter(status='queued').update(status='done')

        self.assertIsNotNone(self.cut())
        self.assertIsNone(self.cut())
        self.assertEqual(book.parts.filter(status='queued').count(), 1)

    def test_books_with_a_queued_part_are_skipped(self):
        busy = self.start_book('busy', [60] * 12)
        svc.enqueue_next_part(busy)
        idle = self.start_book('idle', [60] * 12)

        part = self.cut()

        self.assertEqual(part.audiobook, idle)
        self.assertEqual(busy.parts.filter(status='queued').count(), 1)

    def test_book_that_cannot_cut_a_part_is_dropped(self):
        stuck = self.start_book('stuck', [60, 60, 30])
        ready = self.start_book('ready', [60] * 12)
        now = timezone.now()
        self.set_times(stuck, created=now - timedelta(days=9), enqueued=now - timedelta(days=4))
        self.set_times(ready, created=now - timedelta(days=9), enqueued=now - timedelta(days=1))

        part = self.cut()

        self.assertEqual(part.audiobook, ready)
        self.assertEqual(stuck.parts.count(), 1)

    def test_started_book_pinned_to_another_worker_is_not_cut(self):
        pinned = self.start_book('pinned', [60] * 12)
        Audiobook.objects.filter(pk=pinned.pk).update(worker_id='another-worker')

        self.assertIsNone(self.cut())
        self.assertEqual(pinned.parts.filter(status='queued').count(), 0)

    def test_disk_budget_stops_the_cut(self):
        audiobook = self.start_book('full-disk', [60, 60, 60, 60])
        Audiobook.objects.filter(pk=audiobook.pk).update(total_size_bytes=2 * GB)
        self.make_book('waiting', [60, 60, 60, 60])

        with override_settings(AUDIOBOOK_DISK_BUDGET_GB=1), self.assertLogs('lncrawler_api.audiobooks', 'WARNING'):
            part = self.cut()

        self.assertIsNone(part)
        self.assertEqual(audiobook.parts.filter(status='queued').count(), 0)
        self.assertFalse(Audiobook.objects.filter(novel__slug='waiting').exists())

    def test_new_book_is_the_most_popular_unstarted_one(self):
        self.make_book('low', [60] * 4, views=5)
        self.make_book('high', [60] * 4, views=50)
        self.make_book('middle', [60] * 4, views=10)
        self.make_book('lowest', [60] * 4, views=1)

        first = self.serve()
        second = self.serve()

        self.assertEqual((first, second), ('high', 'middle'))

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
        lotm, _ = self.make_book('lotm', [60] * 4, views=500_000)
        self.add_source(lotm, [60] * 4, 'fr', 300_000)
        self.make_book('martial', [60] * 4, views=600_000)
        self.make_book('other', [60] * 4, views=150_000)
        self.add_source(lotm, [60] * 4, 'de', 990_000)

        ranked = [
            (Novel.objects.get(pk=novel_id).slug, language)
            for novel_id, language, _views in sched._unstarted_pairs(['en', 'fr'])
        ]

        self.assertEqual(ranked, [('martial', 'en'), ('lotm', 'en'), ('lotm', 'fr'), ('other', 'en')])

    def test_only_the_languages_of_the_claim_start_new_books(self):
        self.make_book('english', [60] * 4, views=10)
        novel, _ = self.make_book('french', [60] * 4, views=1_000_000, language='fr')
        self.add_source(novel, [60] * 4, 'de', 1_000_000)

        self.cut(languages=['en'])

        self.assertEqual(set(Audiobook.objects.values_list('language', flat=True)), {'en'})

    def test_no_language_means_no_new_books(self):
        self.make_book('fresh', [60] * 4, views=10)

        self.assertIsNone(self.cut(languages=[]))
        self.assertFalse(Audiobook.objects.exists())

    def test_started_book_in_an_unannounced_language_gets_no_part(self):
        novel, source = self.make_book('french', [60] * 12, language='fr')
        audiobook = Audiobook.objects.create(novel=novel, source=source, language='fr')
        first = svc.enqueue_next_part(audiobook)
        first.status = 'done'
        first.completed_at = timezone.now() - timedelta(days=2)
        first.save()

        self.assertIsNone(self.cut(languages=['en']))
        self.assertEqual(self.parts_of(novel).count(), 1)

    def test_new_book_that_gets_no_part_keeps_its_word_counts(self):
        # Two short chapters of an ongoing source: nothing can be cut, so the new book is rolled back
        novel, source = self.make_book('short', [30, 30], views=10)

        self.assertIsNone(self.cut())

        self.assertFalse(Audiobook.objects.exists())
        self.assertFalse(Chapter.objects.filter(novel_from_source=source, word_count__isnull=True).exists())

    def test_pair_with_an_audiobook_is_skipped_while_the_other_language_starts(self):
        novel, english = self.make_book('split', [60] * 4, views=900_000)
        french = self.add_source(novel, [60] * 4, 'fr', 100_000)
        # Paused, so the English book is not served as a started book either
        Audiobook.objects.create(novel=novel, source=english, language='en', status='paused')

        part = self.cut(languages=['en', 'fr'])

        self.assertEqual(part.audiobook.language, 'fr')
        self.assertFalse(Audiobook.objects.filter(novel=novel, language='en', parts__isnull=False).exists())
        self.assertTrue(Audiobook.objects.filter(novel=novel, language='fr', source=french).exists())

    def test_one_claim_cuts_one_part_of_a_new_book(self):
        self.make_book('one', [60] * 6, views=1)

        self.cut()

        self.assertEqual(AudiobookPart.objects.filter(audiobook__novel__slug='one').count(), 1)

    def test_new_book_scan_gives_up_after_the_novel_limit(self):
        self.make_book('short-a', [20, 20], views=40)
        self.make_book('short-b', [20, 20], views=30)
        self.make_book('short-c', [20, 20], views=20)
        self.make_book('good', [60] * 4, views=1)

        with patch.object(sched, 'NEW_BOOK_NOVEL_LIMIT', 2):
            part = self.cut()

        self.assertIsNone(part)
        self.assertFalse(Audiobook.objects.filter(novel__slug='good').exists())

    def test_new_book_scan_gives_up_after_the_read_limit(self):
        # 'first' reads its 2 chapter files, which reach the limit of 2: the scan stops before 'good'
        self.make_book('first', [20, 20], views=40)
        self.make_book('good', [60] * 4, views=1)

        with patch.object(sched, 'NEW_BOOK_READ_LIMIT', 2):
            part = self.cut()

        self.assertIsNone(part)
        self.assertFalse(Audiobook.objects.filter(novel__slug='good').exists())

    def test_counted_short_novels_do_not_stop_the_scan_before_a_later_one(self):
        for index in range(3):
            _, source = self.make_book(f'short-{index}', [20, 20], views=40 - index)
            Chapter.objects.filter(novel_from_source=source).update(word_count=20)
        self.make_book('good', [60] * 4, views=1)

        # Three counted short novels rank above 'good' and cost only a query each, so 'good' is reached.
        with patch.object(sched, 'NEW_BOOK_NOVEL_LIMIT', 5):
            part = self.cut()

        self.assertEqual(part.audiobook.novel.slug, 'good')

    def test_clash_on_one_novel_is_logged_and_the_cut_goes_on(self):
        self.make_book('clash', [60] * 4, views=40)
        self.make_book('good', [60] * 4, views=1)
        real = svc.get_or_create_audiobook

        def clash(novel, language='en', source=None):
            if novel.slug == 'clash':
                raise IntegrityError('duplicate key')
            return real(novel, language, source=source)

        with patch.object(svc, 'get_or_create_audiobook', side_effect=clash), \
                self.assertLogs('lncrawler_api.audiobooks', 'WARNING'):
            part = self.cut()

        self.assertEqual(part.audiobook.novel.slug, 'good')
        self.assertEqual(set(Audiobook.objects.values_list('novel__slug', flat=True)), {'good'})

    def test_dmca_non_english_and_short_novels_are_skipped(self):
        self.make_book('dmca', [60] * 4, views=40, dmca=True)
        self.make_book('japanese', [60] * 4, views=30, language='ja')
        self.make_book('short', [20, 20], views=20)
        self.make_book('good', [60] * 4, views=1)

        part = self.cut()

        self.assertEqual(part.audiobook.novel.slug, 'good')
        self.assertEqual(set(Audiobook.objects.values_list('novel__slug', flat=True)), {'good'})

    def test_novel_with_too_few_words_for_a_full_part_leaves_no_row(self):
        # 60 words, but a tail is not cut for a source that is still ongoing
        self.make_book('tail', [30, 30], views=1)

        self.assertIsNone(self.cut())
        self.assertFalse(Audiobook.objects.filter(novel__slug='tail').exists())

    def test_paused_and_retired_audiobooks_are_untouched(self):
        for slug, status in (('paused', 'paused'), ('retired', 'retired')):
            novel, source = self.make_book(slug, [60] * 4, views=10)
            Audiobook.objects.create(novel=novel, source=source, status=status)

        self.assertIsNone(self.cut())

        self.assertFalse(AudiobookPart.objects.filter(audiobook__novel__slug__in=['paused', 'retired']).exists())
        self.assertEqual(Audiobook.objects.get(novel__slug='paused').status, 'paused')
        self.assertEqual(Audiobook.objects.get(novel__slug='retired').status, 'retired')


class RotationShareTests(SchedulerBase):
    def new_books_started(self, prefix, started_count, runs=10):
        """New books started over ``runs`` claims that each cut one part, with ``started_count`` books already in
        rotation. The workers finish every queued part between two claims."""
        now = timezone.now()
        for index in range(started_count):
            book = self.start_book(f'{prefix}-started-{index}', [60] * 12)
            self.set_times(book, created=now - timedelta(days=10), enqueued=now - timedelta(days=5 - index))
        for index in range(runs):
            self.make_book(f'{prefix}-fresh-{index}', [60] * 12, views=100 - index)
        for _ in range(runs):
            self.serve()
        return Audiobook.objects.filter(novel__slug__startswith=f'{prefix}-fresh').count()

    def test_new_slot_and_started_book_alternate(self):
        started = self.start_book('alt-started', [60] * 12)
        now = timezone.now()
        # The new slot's newest audiobook is older than the started book's last part, so the slot goes first.
        self.set_times(started, created=now - timedelta(days=10), enqueued=now - timedelta(days=5))
        self.make_book('alt-new-a', [60] * 12, views=20)
        self.make_book('alt-new-b', [60] * 12, views=10)

        served = [self.serve() for _ in range(3)]

        self.assertEqual(served, ['alt-new-a', 'alt-started', 'alt-new-b'])

    def test_more_books_in_rotation_mean_fewer_new_books(self):
        alone = self.new_books_started('one', 1)
        Audiobook.objects.all().delete()
        Novel.objects.all().delete()

        crowded = self.new_books_started('four', 4)

        self.assertEqual((alone, crowded), (4, 2))


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
            name='audiobook_housekeeping', interval_seconds=3600, next_run_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.get(reverse("admin:lncrawler_api_audiobook_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'audiobook_housekeeping')
        self.assertContains(response, 'Queued words:')
        self.assertContains(response, 'Started books in rotation')
        self.assertNotContains(response, 'enqueue_audiobooks')
