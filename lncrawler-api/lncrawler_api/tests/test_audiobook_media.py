"""Audiobooks phase 4: the cover, the tags of the chapter files, the .m4b builds, the cache and its pruning,
the .m4b jobs, and the admin download and actions."""

import hashlib
import io
import json
import os
import shutil
import subprocess
import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus
from PIL import Image

from ..models import Author, AudiobookChapter, Job
from ..services import audiobook_cover, audiobook_m4b, audiobook_media, audiobook_service as svc
from ..services.audiobook_m4b import M4bBuildError, enqueue_m4b_job, m4b_job_key, run_m4b_job
from ..services.audiobook_scheduler import audiobook_housekeeping
from . import test_audiobook_worker_api as worker_tests
from .test_audiobooks import AudiobookBase

HOUR = 60 * 60
SITE_DISCLAIMER = "Generated audiobook made from the site text with generated voices. Not an official audiobook."


def make_opus(path, seconds):
    """Encode a tone into an Opus file with ffmpeg, the same kind of chapter file a worker uploads."""
    subprocess.run(
        ['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=220:sample_rate=48000',
         '-t', str(seconds), '-ac', '1', '-ar', '48000', '-c:a', 'libopus', '-b:a', '24k', path],
        check=True, timeout=120,
    )


def probe(path):
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-print_format', 'json', '-show_streams', '-show_chapters', path],
        capture_output=True, text=True, check=True, timeout=60,
    )
    return json.loads(result.stdout)


def write_bytes(path, size, age=0):
    """A file of ``size`` bytes whose mtime is ``age`` seconds old."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as handle:
        handle.write(b'x' * size)
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))
    return path


class CoverTests(AudiobookBase):
    def setUp(self):
        super().setUp()
        self.source = self.make_source()
        self.source_file = os.path.join(self.tmp, 'foo', 'site', 'cover.jpg')
        Image.new('RGB', (400, 600), (30, 120, 200)).save(self.source_file, format='JPEG')
        self.source.cover_path = 'foo/site/cover.jpg'
        self.source.save(update_fields=['cover_path'])
        self.audiobook = self.make_audiobook(self.source)

    def test_build_writes_the_jpg_and_the_thumb(self):
        path = audiobook_cover.build_cover(self.audiobook)

        self.assertTrue(path.endswith('cover.jpg'))
        self.audiobook.refresh_from_db()
        self.assertEqual(self.audiobook.cover_path, path)
        with Image.open(os.path.join(self.tmp, path)) as jpg:
            self.assertEqual((jpg.format, jpg.size), ('JPEG', (1400, 1400)))
        thumb = os.path.join(self.tmp, audiobook_cover.thumb_path(self.audiobook))
        with Image.open(thumb) as webp:
            self.assertEqual((webp.format, webp.size), ('WEBP', (600, 600)))

    def test_without_a_source_cover_the_title_is_used(self):
        self.source.cover_path = None
        self.source.save(update_fields=['cover_path'])
        os.remove(self.source_file)

        path = audiobook_cover.build_cover(self.audiobook)

        with Image.open(os.path.join(self.tmp, path)) as jpg:
            self.assertEqual(jpg.size, (1400, 1400))

    def test_part_cover_is_a_jpeg_with_a_badge(self):
        plain = audiobook_cover.build_cover(self.audiobook)
        with open(os.path.join(self.tmp, plain), 'rb') as handle:
            plain_bytes = handle.read()

        data = audiobook_cover.part_cover_jpeg(self.audiobook, 3)

        self.assertTrue(data.startswith(b'\xff\xd8'))
        with Image.open(io.BytesIO(data)) as badge:
            self.assertEqual((badge.format, badge.size), ('JPEG', (1400, 1400)))
        self.assertNotEqual(data, plain_bytes)

    def test_stale_follows_the_jpg_and_the_source_mtime(self):
        self.assertTrue(audiobook_cover.cover_is_stale(self.audiobook))

        audiobook_cover.build_cover(self.audiobook)
        self.assertFalse(audiobook_cover.cover_is_stale(self.audiobook))

        later = time.time() + 60
        os.utime(self.source_file, (later, later))
        self.assertTrue(audiobook_cover.cover_is_stale(self.audiobook))

    def test_a_stamp_without_the_cover_version_is_stale(self):
        audiobook_cover.build_cover(self.audiobook)
        current = audiobook_cover._source_stamp(self.audiobook)
        with open(audiobook_cover._stamp_path(self.audiobook), 'w', encoding='utf-8') as handle:
            handle.write(current.split('\n', 1)[1])

        self.assertTrue(audiobook_cover.cover_is_stale(self.audiobook))

    def test_a_cover_replaced_with_an_older_file_is_stale(self):
        audiobook_cover.build_cover(self.audiobook)
        earlier = time.time() - HOUR
        os.utime(self.source_file, (earlier, earlier))

        self.assertTrue(audiobook_cover.cover_is_stale(self.audiobook))

    def test_a_corrupt_source_falls_back_to_the_title_square(self):
        with open(self.source_file, 'wb') as handle:
            handle.write(b'not an image at all')

        with patch.object(audiobook_cover, '_title_square', wraps=audiobook_cover._title_square) as title:
            path = audiobook_cover.build_cover(self.audiobook)

        title.assert_called_once()
        with Image.open(os.path.join(self.tmp, path)) as jpg:
            self.assertEqual(jpg.size, (1400, 1400))

    def test_a_valid_source_is_used(self):
        with patch.object(audiobook_cover, '_title_square', wraps=audiobook_cover._title_square) as title:
            audiobook_cover.build_cover(self.audiobook)

        title.assert_not_called()

    def test_an_oversize_source_falls_back_to_the_title_square(self):
        with patch.object(audiobook_cover, 'MAX_SOURCE_PIXELS', 100), \
                patch.object(audiobook_cover, '_title_square', wraps=audiobook_cover._title_square) as title:
            audiobook_cover.build_cover(self.audiobook)

        title.assert_called_once()

    def test_a_failed_write_leaves_no_temp_file(self):
        with patch.object(Image.Image, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                audiobook_cover.build_cover(self.audiobook)

        leftovers = [name for name in os.listdir(svc.audio_dir(self.source)) if name.endswith('.tmp')]
        self.assertEqual(leftovers, [])


@override_settings(AUDIOBOOK_ENABLED=True)
class CompleteCoverTests(worker_tests.WorkerBase):
    """The cover is built after the worker's complete commits, and a cover error never fails complete."""

    def setUp(self):
        super().setUp()
        self.claim_part()
        for chapter in self.chapters:
            self.assertIn(self.upload(chapter).status_code, (200, 201))

    def complete(self):
        with self.captureOnCommitCallbacks(execute=True):
            return self.call('post', self.part_url('complete'), data=self.complete_body())

    def test_complete_builds_the_cover(self):
        self.assertEqual(self.complete().status_code, 200)

        self.audiobook.refresh_from_db()
        self.assertTrue(self.audiobook.cover_path.endswith('cover.jpg'))

    def test_a_cover_error_does_not_fail_complete(self):
        with patch('lncrawler_api.services.audiobook_cover.build_cover', side_effect=RuntimeError('boom')):
            response = self.complete()

        self.assertEqual(response.status_code, 200)
        self.part.refresh_from_db()
        self.assertEqual(self.part.status, 'done')


class ListenableBase(AudiobookBase):
    """A source of three chapters and one done part of them, with real Opus chapter files and tags hash set."""

    def setUp(self):
        super().setUp()
        self.source = self.make_source()
        self.chapters = self.add_chapters(self.source, [300, 300, 300])
        self.audiobook = self.make_audiobook(self.source)
        self.part = self.make_part(
            self.audiobook, index=1, chapter_start=1, chapter_end=3, word_count=900, status='done',
            qa_passed=True, duration_s=6.0, generation=1, chapter_ids=[ch.pk for ch in self.chapters],
        )
        self.write_chapter_files()
        self.audiobook.tags_hash = audiobook_media.compute_tags_hash(self.audiobook)
        self.audiobook.save(update_fields=['tags_hash'])

    def write_chapter_files(self):
        directory = os.path.join(svc.audio_dir(self.source), 'part-001', 'g1')
        os.makedirs(directory, exist_ok=True)
        for offset, chapter in enumerate(self.chapters):
            path = os.path.join(directory, f"{chapter.pk:05}.ogg")
            make_opus(path, 2.0)
            with open(path, 'rb') as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            AudiobookChapter.objects.create(
                part=self.part, chapter=chapter, file_path=os.path.relpath(path, self.tmp),
                duration_s=2.0, size_bytes=os.path.getsize(path), sha256=digest, offset_s=2.0 * offset,
            )


class TagTests(ListenableBase):
    def test_hash_follows_the_title_the_authors_and_the_chapters(self):
        first = audiobook_media.compute_tags_hash(self.audiobook)
        self.assertEqual(first, audiobook_media.compute_tags_hash(self.audiobook))

        self.novel.title = "Other title"
        self.novel.save()
        second = audiobook_media.compute_tags_hash(self.audiobook)
        self.assertNotEqual(first, second)

        self.source.authors.add(Author.objects.create(name="Ann"))
        third = audiobook_media.compute_tags_hash(self.audiobook)
        self.assertNotEqual(second, third)

        self.chapters[0].title = "Prologue"
        self.chapters[0].save()
        self.assertNotEqual(third, audiobook_media.compute_tags_hash(self.audiobook))

    def test_retag_rewrites_the_tags_sizes_and_hash(self):
        self.novel.title = "Renamed"
        self.novel.save()

        self.assertEqual(audiobook_media.retag_audiobook(self.audiobook), 3)

        for row in AudiobookChapter.objects.filter(part=self.part):
            path = os.path.join(self.tmp, row.file_path)
            tags = OggOpus(path)
            self.assertEqual(tags['album'], ["Renamed (Generated audiobook) — Part 1"])
            self.assertEqual(tags['comment'], [SITE_DISCLAIMER])
            self.assertEqual(tags['description'], [SITE_DISCLAIMER])
            self.assertEqual(row.size_bytes, os.path.getsize(path))
        self.audiobook.refresh_from_db()
        self.assertEqual(self.audiobook.tags_hash, audiobook_media.compute_tags_hash(self.audiobook))

    def test_a_missing_chapter_file_is_skipped(self):
        first = self.part.chapters.order_by('offset_s').first()
        os.remove(os.path.join(self.tmp, first.file_path))

        self.assertEqual(audiobook_media.retag_audiobook(self.audiobook), 2)

    def test_recreated_chapter_rows_keep_the_tags_hash(self):
        before = audiobook_media.compute_tags_hash(self.audiobook)
        rows = list(AudiobookChapter.objects.filter(part=self.part).order_by('pk'))
        AudiobookChapter.objects.filter(part=self.part).delete()
        for row in rows:
            row.pk = None
            row.save()

        self.assertEqual(audiobook_media.compute_tags_hash(self.audiobook), before)

    def test_retag_leaves_no_temp_files(self):
        self.novel.title = "Renamed"
        self.novel.save()

        audiobook_media.retag_audiobook(self.audiobook)

        folder = os.path.join(svc.audio_dir(self.source), 'part-001', 'g1')
        names = [os.path.basename(row.file_path) for row in AudiobookChapter.objects.filter(part=self.part)]
        self.assertEqual(sorted(os.listdir(folder)), sorted(names))

    def test_a_failed_tagging_leaves_the_original_intact(self):
        self.novel.title = "Renamed"
        self.novel.save()
        folder = os.path.join(svc.audio_dir(self.source), 'part-001', 'g1')
        originals = {}
        for row in AudiobookChapter.objects.filter(part=self.part):
            with open(os.path.join(self.tmp, row.file_path), 'rb') as handle:
                originals[row.file_path] = handle.read()

        with patch.object(audiobook_media, 'tag_chapter_file', side_effect=RuntimeError('disk full')):
            with self.assertRaises(RuntimeError):
                audiobook_media.retag_audiobook(self.audiobook)

        for file_path, data in originals.items():
            with open(os.path.join(self.tmp, file_path), 'rb') as handle:
                self.assertEqual(handle.read(), data)
        self.assertEqual(sorted(os.listdir(folder)), sorted(os.path.basename(p) for p in originals))


@override_settings(AUDIOBOOK_ENABLED=True)
class TagHousekeepingTests(ListenableBase):
    def test_housekeeping_retags_only_when_the_hash_differs(self):
        self.audiobook.tags_hash = ''
        self.audiobook.save(update_fields=['tags_hash'])

        self.assertEqual(audiobook_housekeeping()['retagged'], 1)
        self.audiobook.refresh_from_db()
        self.assertEqual(self.audiobook.tags_hash, audiobook_media.compute_tags_hash(self.audiobook))

        self.assertEqual(audiobook_housekeeping()['retagged'], 0)


class M4bBuildTests(ListenableBase):
    def test_build_writes_a_listenable_file_per_format(self):
        for fmt in audiobook_m4b.FORMATS:
            with self.subTest(fmt=fmt):
                path = audiobook_m4b.build_m4b(self.part, fmt)

                self.assertEqual(
                    os.path.basename(path),
                    f"part-001-g1-{fmt}-{self.audiobook.tags_hash[:10]}-{audiobook_cover.cover_key(self.audiobook)}.m4b",
                )
                info = probe(path)
                self.assertEqual(info['streams'][0]['codec_name'], 'opus' if fmt == 'opus' else 'aac')
                self.assertEqual(info['streams'][0]['channels'], 1)

                tags = MP4(path).tags
                self.assertEqual(tags['\xa9nam'], ["Foo (Generated audiobook) — Part 1 (Ch. 1–3)"])
                self.assertEqual(tags['\xa9alb'], ["Foo (Generated audiobook)"])
                self.assertEqual(tags['\xa9cmt'], [SITE_DISCLAIMER])
                self.assertEqual(tags['desc'], [SITE_DISCLAIMER])
                self.assertEqual(tags['\xa9wrt'], ["Generated voices (LNCrawler)"])
                self.assertEqual(tags['trkn'], [(1, 1)])
                self.assertEqual(tags['stik'], [2])
                self.assertEqual(tags['\xa9mvi'], [1])
                self.assertEqual(tags['----:com.apple.iTunes:LANGUAGE'][0], b'en')
                self.assertEqual(tags['covr'][0].imageformat, MP4Cover.FORMAT_JPEG)
                chapters = info['chapters']
                self.assertEqual([c['tags']['title'] for c in chapters], ['Chapter 1', 'Chapter 2', 'Chapter 3'])
                for index, chapter in enumerate(chapters):
                    self.assertAlmostEqual(float(chapter['start_time']), 2.0 * index, delta=0.1)

    def test_cached_file_is_returned_and_touched(self):
        path = audiobook_m4b.build_m4b(self.part, 'opus')
        old = time.time() - HOUR
        os.utime(path, (old, old))

        self.assertEqual(audiobook_m4b.cached_m4b(self.part, 'opus'), path)
        self.assertGreater(os.path.getmtime(path), old)

    def test_a_new_tags_hash_is_a_cache_miss(self):
        audiobook_m4b.build_m4b(self.part, 'aac')

        self.audiobook.tags_hash = 'f' * 64
        self.assertIsNone(audiobook_m4b.cached_m4b(self.part, 'aac'))

    def test_a_part_that_is_not_done_is_refused(self):
        self.part.status = 'claimed'
        self.part.save()

        with self.assertRaises(ValueError):
            audiobook_m4b.build_m4b(self.part, 'opus')

    def test_an_unknown_format_is_refused(self):
        with self.assertRaises(ValueError):
            audiobook_m4b.build_m4b(self.part, 'mp3')

    def test_an_ffmpeg_failure_is_an_error_with_the_output(self):
        first = self.part.chapters.order_by('offset_s').first()
        os.remove(os.path.join(self.tmp, first.file_path))

        with self.assertRaisesRegex(M4bBuildError, 'ffmpeg failed'):
            audiobook_m4b.build_m4b(self.part, 'opus')

    def test_a_new_source_cover_is_a_cache_miss_with_the_new_art(self):
        cover = os.path.join(self.tmp, 'foo', 'site', 'cover.jpg')
        os.makedirs(os.path.dirname(cover), exist_ok=True)
        Image.new('RGB', (400, 600), (30, 120, 200)).save(cover, format='JPEG')
        self.source.cover_path = 'foo/site/cover.jpg'
        self.source.save(update_fields=['cover_path'])
        first = audiobook_m4b.build_m4b(self.part, 'opus')
        first_art = bytes(MP4(first).tags['covr'][0])

        Image.new('RGB', (400, 600), (200, 40, 40)).save(cover, format='JPEG')
        later = time.time() + 60
        os.utime(cover, (later, later))

        self.assertIsNone(audiobook_m4b.cached_m4b(self.part, 'opus'))
        second = audiobook_m4b.build_m4b(self.part, 'opus')
        self.assertNotEqual(os.path.basename(first), os.path.basename(second))
        self.assertNotEqual(bytes(MP4(second).tags['covr'][0]), first_art)

    def test_chapter_titles_with_special_characters_survive_the_build(self):
        self.chapters[0].title = 'a=b;c#d\\e "q" \'x\'\nline2'
        self.chapters[0].save()

        path = audiobook_m4b.build_m4b(self.part, 'opus')

        self.assertEqual(probe(path)['chapters'][0]['tags']['title'], 'a=b;c#d\\e "q" \'x\' line2')

    def test_concat_paths_quote_the_apostrophe(self):
        self.assertEqual(
            audiobook_m4b._escape_concat("/a/it's a test/x.ogg"), "file '/a/it'\\''s a test/x.ogg'",
        )

    def test_chapter_files_in_a_folder_with_an_apostrophe_and_a_space(self):
        folder = os.path.join(svc.audio_dir(self.source), "it's a test")
        os.makedirs(folder)
        for row in AudiobookChapter.objects.filter(part=self.part):
            target = os.path.join(folder, os.path.basename(row.file_path))
            shutil.move(os.path.join(self.tmp, row.file_path), target)
            row.file_path = os.path.relpath(target, self.tmp)
            row.save(update_fields=['file_path'])

        path = audiobook_m4b.build_m4b(self.part, 'opus')

        self.assertEqual(len(probe(path)['chapters']), 3)


class DownloadNameTests(ListenableBase):
    def test_plain_name(self):
        self.assertEqual(audiobook_m4b.download_filename(self.part), "Foo - Part 01 (Ch. 1-3) [generated].m4b")

    def test_unsafe_characters_are_dropped(self):
        self.novel.title = 'Bad/Name?: The "Long" Title'
        self.novel.save()

        self.assertEqual(
            audiobook_m4b.download_filename(self.part),
            "BadName The Long Title - Part 01 (Ch. 1-3) [generated].m4b",
        )

    def test_length_is_capped(self):
        self.novel.title = 'x' * 200
        self.novel.save()

        name = audiobook_m4b.download_filename(self.part)

        self.assertLessEqual(len(name), audiobook_m4b.MAX_NAME)
        self.assertTrue(name.endswith('.m4b'))


class JobTests(ListenableBase):
    def test_enqueue_reuses_the_active_job_per_format(self):
        first = enqueue_m4b_job(self.part, 'opus')
        second = enqueue_m4b_job(self.part, 'opus')
        aac = enqueue_m4b_job(self.part, 'aac')

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.job_type, Job.JOB_TYPE_M4B)
        self.assertEqual(first.query, m4b_job_key(self.part.pk, 'opus'))
        self.assertNotEqual(aac.pk, first.pk)

    def test_one_active_job_per_key(self):
        key = m4b_job_key(self.part.pk, 'opus')
        Job.objects.create(job_type=Job.JOB_TYPE_M4B, status=Job.STATUS_CREATED, query=key)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Job.objects.create(job_type=Job.JOB_TYPE_M4B, status=Job.STATUS_DOWNLOADING, query=key)

        Job.objects.create(job_type='epub', status=Job.STATUS_CREATED, query='epub-key')

    def test_run_completes_the_job_with_the_download_name(self):
        job = enqueue_m4b_job(self.part, 'aac')

        run_m4b_job(job.pk, job.query)

        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_DOWNLOAD_COMPLETED)
        self.assertEqual(job.output_path, audiobook_m4b._cache_path(self.part, 'aac'))
        self.assertTrue(os.path.isfile(job.output_path))

    def test_a_failure_is_recorded_on_the_job(self):
        self.part.status = 'claimed'
        self.part.save()
        job = enqueue_m4b_job(self.part, 'opus')

        run_m4b_job(job.pk, job.query)

        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_FAILED)
        self.assertIn('listenable', job.error_message)

    def test_claim_sql_runs_m4b_jobs_as_downloads(self):
        import crawler_supervisor

        self.assertRegex(
            crawler_supervisor.CLAIM_SQL,
            r"WHEN job\.job_type IN \('download', 'epub', 'm4b'\) THEN 'downloading'",
        )

    def test_m4b_jobs_are_hidden_from_the_job_list(self):
        enqueue_m4b_job(self.part, 'opus')

        response = self.client.get(reverse('list_jobs'))

        self.assertEqual(response.json()['jobs'], [])


class PruneTests(ListenableBase):
    def setUp(self):
        super().setUp()
        audiobook_cover.build_cover(self.audiobook)
        self.cover = audiobook_cover.cover_key(self.audiobook)

    def cache_file(self, name, size=1000, age=0):
        return write_bytes(os.path.join(audiobook_m4b._cache_dir(self.audiobook), name), size, age)

    def test_names_no_part_uses_any_more_are_removed(self):
        stale = self.cache_file('part-001-g9-opus-0123456789-89abcdef.m4b', age=HOUR)
        current = self.cache_file(audiobook_m4b._cache_name(self.part, 'opus', self.cover), age=HOUR)

        result = audiobook_m4b.prune_m4b_cache()

        self.assertFalse(os.path.exists(stale))
        self.assertTrue(os.path.exists(current))
        self.assertEqual(result['removed'], 1)

    def test_young_files_and_the_kept_file_stay(self):
        young = self.cache_file('part-001-g9-opus-0123456789-89abcdef.m4b', age=60)
        kept = self.cache_file('part-001-g8-aac-0123456789-89abcdef.m4b', age=HOUR)

        audiobook_m4b.prune_m4b_cache(keep=kept)

        self.assertTrue(os.path.exists(young))
        self.assertTrue(os.path.exists(kept))

    @override_settings(AUDIOBOOK_M4B_CACHE_GB=2000 / 1024 ** 3)
    def test_least_recently_used_go_first_until_under_the_cap(self):
        opus = self.cache_file(audiobook_m4b._cache_name(self.part, 'opus', self.cover), size=1500, age=2 * HOUR)
        aac = self.cache_file(audiobook_m4b._cache_name(self.part, 'aac', self.cover), size=1500, age=HOUR)

        result = audiobook_m4b.prune_m4b_cache()

        self.assertFalse(os.path.exists(opus))
        self.assertTrue(os.path.exists(aac))
        self.assertEqual(result, {'removed': 1, 'freed_bytes': 1500, 'cache_bytes': 1500})
        self.assertEqual(audiobook_m4b.m4b_cache_bytes(), 1500)

    def test_stray_tmp_files_are_removed_after_a_day(self):
        old = self.cache_file('part-001-g1-opus-0123456789.m4b.tmp', age=2 * 24 * HOUR)
        young = self.cache_file('part-001-g1-aac-0123456789.m4b.tmp', age=HOUR)

        audiobook_m4b.prune_m4b_cache()

        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(young))

    def test_stale_lock_files_are_removed_after_a_day(self):
        old = self.cache_file('part-001-g1-opus-0123456789.m4b.lock', age=2 * 24 * HOUR)
        young = self.cache_file('part-001-g1-aac-0123456789.m4b.lock', age=HOUR)

        audiobook_m4b.prune_m4b_cache()

        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(young))

    def test_only_the_audiobook_cache_folders_are_walked(self):
        outside = write_bytes(os.path.join(self.tmp, 'foo', 'site', 'other.m4b'), 1000, HOUR)

        audiobook_m4b.prune_m4b_cache()

        self.assertTrue(os.path.exists(outside))

    def test_names_that_do_not_parse_go_after_a_day(self):
        old_scheme = self.cache_file('part-001-g1-opus-0123456789.m4b', age=2 * 24 * HOUR)
        young_scheme = self.cache_file('part-001-g1-aac-0123456789.m4b', age=2 * HOUR)

        audiobook_m4b.prune_m4b_cache()

        self.assertFalse(os.path.exists(old_scheme))
        self.assertTrue(os.path.exists(young_scheme))


class AdminM4bTests(ListenableBase):
    def setUp(self):
        super().setUp()
        self.admin_user = get_user_model().objects.create_superuser("audio-admin", "audio@example.com", "pw")
        self.client.force_login(self.admin_user)

    def m4b_url(self, fmt):
        return reverse('admin:lncrawler_api_audiobookpart_m4b', args=[self.part.pk, fmt])

    def test_download_enqueues_then_serves_the_cached_file(self):
        response = self.client.get(self.m4b_url('opus'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Job.objects.filter(query=m4b_job_key(self.part.pk, 'opus')).count(), 1)

        audiobook_m4b.build_m4b(self.part, 'opus')
        response = self.client.get(self.m4b_url('opus'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn(audiobook_m4b.download_filename(self.part), response['Content-Disposition'])

    def test_non_staff_users_are_denied(self):
        self.client.logout()
        reader = get_user_model().objects.create_user("reader", "reader@example.com", "pw")
        self.client.force_login(reader)

        response = self.client.get(self.m4b_url('opus'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response['Location'])
        self.assertEqual(Job.objects.filter(job_type=Job.JOB_TYPE_M4B).count(), 0)

    def test_rebuild_cover_action(self):
        url = reverse('admin:lncrawler_api_audiobook_changelist')

        self.client.post(url, {'action': 'rebuild_cover', '_selected_action': [self.audiobook.pk]})

        self.audiobook.refresh_from_db()
        self.assertTrue(self.audiobook.cover_path.endswith('cover.jpg'))

    def test_retag_files_action(self):
        self.audiobook.tags_hash = ''
        self.audiobook.save(update_fields=['tags_hash'])
        url = reverse('admin:lncrawler_api_audiobook_changelist')

        self.client.post(url, {'action': 'retag_files', '_selected_action': [self.audiobook.pk]})

        self.audiobook.refresh_from_db()
        self.assertEqual(self.audiobook.tags_hash, audiobook_media.compute_tags_hash(self.audiobook))
