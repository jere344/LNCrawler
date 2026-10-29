"""Audiobooks phase 3: the worker API (claim, EPUB, chapter upload, complete, fail, ping), the worker
accounts, the leftover housekeeping, and the fake worker end to end."""

import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from mutagen.oggopus import OggOpus
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from ..models import (
    Audiobook,
    AudiobookChapter,
    AudiobookPart,
    AudiobookWorker,
    Chapter,
    Novel,
)
from ..services import audiobook_media
from ..services import audiobook_scheduler as sched
from ..services import audiobook_service as svc
from ..views import audiobook_worker_views as views
from ..services.audiobook_worker_auth import WORKER_GROUP, IsAudiobookWorker, ensure_worker_token
from .helpers import make_novel, make_source as make_source_row, write_chapter
from .test_audiobooks import AudiobookBase

WORKER = 'w1'  # worker id of the worker under test
OTHER_WORKER = 'w2'  # a second worker, to test ownership
SITE_DISCLAIMER = "Generated audiobook made from the site text with generated voices. Not an official audiobook."
FIXTURE_SECONDS = 11.5  # length of the valid fixtures: above the 10 s minimum, below any cut-off
VALID_FIXTURE_ARGS = ['-ac', '1', '-ar', '48000', '-c:a', 'libopus', '-b:a', '24k', '-vbr', 'on']


def _make_fixture(directory, name, seconds, args):
    """Encode a tone with ffmpeg into ``directory/name`` and return its bytes."""
    path = os.path.join(directory, name)
    subprocess.run(
        ['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=220:sample_rate=48000',
         '-t', str(seconds), *args, path],
        check=True, timeout=120,
    )
    with open(path, 'rb') as handle:
        return handle.read()


class WorkerBase(AudiobookBase):
    """One queued part of two chapters, and a worker token. Every call goes through the API."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        fixture_dir = tempfile.mkdtemp(prefix='worker-fixtures-')
        cls.addClassCleanup(shutil.rmtree, fixture_dir, True)
        cls.fixtures = {
            'valid': _make_fixture(fixture_dir, 'valid.ogg', FIXTURE_SECONDS, VALID_FIXTURE_ARGS),
            'stereo': _make_fixture(
                fixture_dir, 'stereo.ogg', FIXTURE_SECONDS,
                ['-ac', '2', '-ar', '48000', '-c:a', 'libopus', '-b:a', '24k', '-vbr', 'on'],
            ),
            'mp3': _make_fixture(
                fixture_dir, 'mono.mp3', FIXTURE_SECONDS,
                ['-ac', '1', '-ar', '48000', '-c:a', 'libmp3lame', '-b:a', '64k'],
            ),
            'loud': _make_fixture(
                fixture_dir, 'loud.ogg', FIXTURE_SECONDS,
                ['-ac', '1', '-ar', '48000', '-c:a', 'libopus', '-b:a', '96k', '-vbr', 'on'],
            ),
            'short': _make_fixture(fixture_dir, 'short.ogg', 5, VALID_FIXTURE_ARGS),
        }

    def setUp(self):
        super().setUp()
        self.source = self.make_source()
        self.chapters = self.add_chapters(self.source, [300, 300])
        self.audiobook = self.make_audiobook(self.source)
        self.part = self.make_part(
            self.audiobook, index=1, chapter_start=1, chapter_end=2, word_count=600,
            chapter_ids=[ch.pk for ch in self.chapters],
        )
        self.key, _ = ensure_worker_token('worker-a')
        self.other_key, _ = ensure_worker_token('worker-b')

    def call(self, method, url, data=None, raw=None, key=None, worker_id=WORKER, headers=None):
        """One request as a worker: token, contract version and, unless None, the X-Worker-Id header."""
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {key or self.key}')
        extra = {'HTTP_X_WORKER_CONTRACT': '1', **(headers or {})}
        if worker_id is not None:
            extra['HTTP_X_WORKER_ID'] = worker_id
        if raw is not None:
            return client.generic(method, url, raw, 'audio/ogg', **extra)
        return client.generic(method, url, json.dumps(data or {}).encode(), 'application/json', **extra)

    def claim_url(self):
        return reverse('audiobook_worker_claim')

    def part_url(self, name, part=None):
        return reverse(f'audiobook_worker_{name}', args=[(part or self.part).pk])

    def claim_body(self):
        return {'worker_id': WORKER, 'version': '1.0'}

    def claim_part(self):
        """Hand the part to the worker the way a claim does, without going through the API."""
        now = timezone.now()
        self.part.status = 'claimed'
        self.part.worker_id = WORKER
        self.part.claimed_at = now
        self.part.lease_until = now + timedelta(seconds=svc.LEASE_SECONDS)
        self.part.generation = 1
        self.part.uploads = {}
        self.part.save()

    def upload(self, chapter, data=None, sha256=None, key=None, worker_id=WORKER, part=None):
        data = self.fixtures['valid'] if data is None else data
        sha256 = sha256 or hashlib.sha256(data).hexdigest()
        url = reverse('audiobook_worker_chapter', args=[(part or self.part).pk, chapter.pk])
        return self.call('put', url, raw=data, key=key, worker_id=worker_id, headers={'HTTP_X_CONTENT_SHA256': sha256})

    def audio_path(self, chapter, generation=1):
        return os.path.join(
            svc.audio_dir(self.source), f'part-{self.part.index:03}', f'g{generation}', f'{chapter.pk:05}.ogg',
        )

    def complete_body(self, qa_passed=True):
        return {
            'cast': {'Narrator': {'engine': 'kokoro', 'voice': 'af', 'role': 'narrator'}},
            'qa': {'passed': qa_passed, 'checks': {}, 'notes': ''},
            'engine': 'castwright+kokoro',
            'engine_version': 'castwright@test kokoro-v1',
        }


@override_settings(AUDIOBOOK_ENABLED=True)
class AuthTests(WorkerBase):
    def test_anonymous_is_401(self):
        response = APIClient().post(self.claim_url(), self.claim_body(), format='json')
        self.assertEqual(response.status_code, 401)

    def test_normal_user_is_403(self):
        user = get_user_model().objects.create_user(username='reader', email='reader@example.com', password='x')
        key = Token.objects.create(user=user).key
        response = self.call('post', self.claim_url(), data=self.claim_body(), key=key, worker_id=None)
        self.assertEqual(response.status_code, 403)

    def test_worker_is_allowed(self):
        response = self.call('post', self.claim_url(), data=self.claim_body(), worker_id=None)
        self.assertEqual(response.status_code, 200)

    def test_permission_checks_the_group(self):
        user = get_user_model().objects.create_user(username='plain', email='plain@example.com', password='x')
        request = SimpleNamespace(user=user)
        self.assertFalse(IsAudiobookWorker().has_permission(request, None))
        user.groups.add(Group.objects.get_or_create(name=WORKER_GROUP)[0])
        self.assertTrue(IsAudiobookWorker().has_permission(request, None))


class ContractHeaderTests(WorkerBase):
    def test_other_contract_version_is_400(self):
        response = self.call('post', self.claim_url(), data=self.claim_body(), headers={'HTTP_X_WORKER_CONTRACT': '2'}, worker_id=None)
        self.assertEqual(response.status_code, 400)
        self.assertIn('contract', response.json()['detail'])


@override_settings(AUDIOBOOK_ENABLED=True)
class ClaimTests(WorkerBase):
    def test_disabled_returns_204_with_retry_after_600(self):
        with override_settings(AUDIOBOOK_ENABLED=False):
            response = self.call('post', self.claim_url(), data=self.claim_body(), worker_id=None)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response['Retry-After'], '600')
        self.part.refresh_from_db()
        self.assertEqual(self.part.status, 'queued')

    def test_nothing_to_claim_returns_204_with_retry_after_300(self):
        self.claim_part()
        response = self.call('post', self.claim_url(), data=self.claim_body(), worker_id=None)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response['Retry-After'], '300')

    def test_claim_still_gets_the_part_when_an_old_worker_sends_an_unknown_key(self):
        body = {**self.claim_body(), 'engine_profiles': ['something-unknown']}
        response = self.call('post', self.claim_url(), data=body, worker_id=None)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['part_id'], str(self.part.pk))

    def test_pinned_audiobook_is_not_offered_to_another_worker(self):
        self.audiobook.worker_id = OTHER_WORKER
        self.audiobook.save()
        response = self.call('post', self.claim_url(), data=self.claim_body(), worker_id=None)
        self.assertEqual(response.status_code, 204)
        self.part.refresh_from_db()
        self.assertEqual(self.part.status, 'queued')

    def pin_to_other(self, days_since_contact):
        AudiobookWorker.objects.update_or_create(
            worker_id=OTHER_WORKER, defaults={'last_seen_at': timezone.now() - timedelta(days=days_since_contact)},
        )
        Audiobook.objects.filter(pk=self.audiobook.pk).update(worker_id=OTHER_WORKER)

    def test_pin_is_kept_while_the_pinned_worker_was_seen_within_seven_days(self):
        self.pin_to_other(6)

        response = self.call('post', self.claim_url(), data=self.claim_body(), worker_id=None)

        self.assertEqual(response.status_code, 204)
        self.part.refresh_from_db()
        self.assertEqual(self.part.status, 'queued')

    def test_pin_is_released_after_seven_days_without_contact(self):
        self.pin_to_other(8)

        response = self.call('post', self.claim_url(), data=self.claim_body(), worker_id=None)

        self.assertEqual(response.status_code, 200)
        self.audiobook.refresh_from_db()
        self.assertEqual(self.audiobook.worker_id, WORKER)

    def test_claim_offers_only_the_announced_languages(self):
        Audiobook.objects.filter(pk=self.audiobook.pk).update(language='fr')
        body = {**self.claim_body(), 'languages': ['en']}

        self.assertEqual(self.call('post', self.claim_url(), data=body, worker_id=None).status_code, 204)

        body['languages'] = ['FR', 'de']
        self.assertEqual(self.call('post', self.claim_url(), data=body, worker_id=None).status_code, 200)

    def test_missing_languages_mean_english_only(self):
        Audiobook.objects.filter(pk=self.audiobook.pk).update(language='fr')

        response = self.call('post', self.claim_url(), data=self.claim_body(), worker_id=None)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(AudiobookWorker.objects.get(worker_id=WORKER).languages, ['en'])

    def test_bad_languages_are_400(self):
        for languages in ('en', ['en', 3], ['en'] * 21):
            body = {**self.claim_body(), 'languages': languages}
            response = self.call('post', self.claim_url(), data=body, worker_id=None)
            self.assertEqual(response.status_code, 400, languages)

    def test_first_claim_pins_the_audiobook(self):
        response = self.call('post', self.claim_url(), data=self.claim_body(), worker_id=None)
        self.assertEqual(response.status_code, 200)
        self.audiobook.refresh_from_db()
        self.assertEqual(self.audiobook.worker_id, WORKER)
        self.part.refresh_from_db()
        self.assertEqual((self.part.status, self.part.worker_id), ('claimed', WORKER))

    def test_priority_order(self):
        second = self.make_part(self.audiobook, index=2, chapter_start=3, chapter_end=3, priority=5)
        response = self.call('post', self.claim_url(), data=self.claim_body(), worker_id=None)
        self.assertEqual(response.json()['part_id'], str(second.pk))

    def test_generation_increments_and_uploads_reset(self):
        self.part.generation = 3
        self.part.uploads = {'1': {'file_path': 'x', 'sha256': 'x', 'duration_s': 1, 'size_bytes': 1}}
        self.part.save()
        self.call('post', self.claim_url(), data=self.claim_body(), worker_id=None)
        self.part.refresh_from_db()
        self.assertEqual(self.part.generation, 4)
        self.assertEqual(self.part.uploads, {})

    def test_dmca_is_not_offered(self):
        Novel.objects.filter(pk=self.novel.pk).update(is_dmca=True)
        response = self.call('post', self.claim_url(), data=self.claim_body(), worker_id=None)
        self.assertEqual(response.status_code, 204)

    def test_paused_is_not_offered(self):
        Audiobook.objects.filter(pk=self.audiobook.pk).update(status='paused')
        response = self.call('post', self.claim_url(), data=self.claim_body(), worker_id=None)
        self.assertEqual(response.status_code, 204)

    def test_response_matches_the_contract(self):
        self.audiobook.cast = {'Old': {'engine': 'kokoro'}}
        self.audiobook.save()
        response = self.call('post', self.claim_url(), data=self.claim_body(), worker_id=None)
        body = response.json()
        self.assertEqual(
            set(body),
            {'part_id', 'audiobook_id', 'series', 'part', 'chapters', 'epub_url', 'previous_cast', 'lease_until'},
        )
        self.assertEqual(set(body['series']), {'title', 'authors', 'language', 'slug'})
        self.assertEqual(set(body['part']), {'index', 'total_known', 'chapter_start', 'chapter_end', 'word_count'})
        self.assertEqual(body['part']['total_known'], 1)
        self.assertEqual(body['series']['slug'], 'foo')
        self.assertEqual(
            [c['chapter_id'] for c in body['chapters']], [ch.pk for ch in self.chapters],
        )
        self.assertEqual([c['number'] for c in body['chapters']], [1, 2])
        self.assertEqual(set(body['chapters'][0]), {'chapter_id', 'number', 'title', 'word_count'})
        self.assertTrue(body['epub_url'].startswith('http'))
        self.assertTrue(body['epub_url'].endswith(f'/api/audiobook-worker/parts/{self.part.pk}/epub'))
        self.assertEqual(body['previous_cast'], {'Old': {'engine': 'kokoro'}})
        self.assertTrue(body['lease_until'].endswith('Z'))


class ClaimRaceTests(TransactionTestCase):
    """Real threads and connections: a part another transaction holds is skipped, not waited for."""

    @override_settings(AUDIOBOOK_ENABLED=True)
    def test_locked_part_is_skipped(self):
        novel = make_novel('Race', 'race')
        source = make_source_row(novel)
        audiobook = Audiobook.objects.create(novel=novel, source=source)
        locked = AudiobookPart.objects.create(
            audiobook=audiobook, index=1, chapter_start=1, chapter_end=1, priority=10,
        )
        free = AudiobookPart.objects.create(
            audiobook=audiobook, index=2, chapter_start=2, chapter_end=2,
        )
        key, _ = ensure_worker_token('worker-race')
        taken = threading.Event()
        release = threading.Event()

        def hold_the_first_part():
            try:
                with transaction.atomic():
                    AudiobookPart.objects.select_for_update().get(pk=locked.pk)
                    taken.set()
                    release.wait(30)
            finally:
                taken.set()
                connection.close()

        thread = threading.Thread(target=hold_the_first_part)
        thread.start()
        try:
            self.assertTrue(taken.wait(30))
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f'Token {key}')
            response = client.generic(
                'POST', reverse('audiobook_worker_claim'),
                json.dumps({'worker_id': WORKER, 'version': '1'}).encode(),
                'application/json', HTTP_X_WORKER_CONTRACT='1',
            )
        finally:
            release.set()
            thread.join(30)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['part_id'], str(free.pk))


@override_settings(AUDIOBOOK_ENABLED=True)
class EpubTests(WorkerBase):
    def test_epub_has_series_meta_and_chapters_in_order(self):
        self.claim_part()
        response = self.call('get', self.part_url('epub'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/epub+zip')
        archive = zipfile.ZipFile(io.BytesIO(b''.join(response.streaming_content)))
        opf = archive.read('OEBPS/content.opf').decode('utf-8')
        self.assertIn('<meta name="calibre:series" content="Foo"/>', opf)
        self.assertIn('<meta name="calibre:series_index" content="1"/>', opf)
        self.assertIn('<dc:title>Foo — Part 1</dc:title>', opf)
        chapter_files = [name for name in archive.namelist() if 'chapter_' in name]
        self.assertEqual(chapter_files, sorted(chapter_files))
        self.assertEqual(len(chapter_files), 2)

    def test_other_worker_is_409(self):
        self.claim_part()
        response = self.call('get', self.part_url('epub'), worker_id=OTHER_WORKER)
        self.assertEqual(response.status_code, 409)


@override_settings(AUDIOBOOK_ENABLED=True)
class HeartbeatTests(WorkerBase):
    def test_extends_the_lease_and_clamps_progress(self):
        self.claim_part()
        AudiobookPart.objects.filter(pk=self.part.pk).update(lease_until=timezone.now() + timedelta(minutes=1))
        response = self.call(
            'post', self.part_url('heartbeat'),
            data={'progress': 2, 'stage': 'x' * 100, 'message': 'busy'},
        )
        self.assertEqual(response.status_code, 200)
        self.part.refresh_from_db()
        self.assertGreater(self.part.lease_until, timezone.now() + timedelta(minutes=10))
        self.assertEqual(self.part.progress, 1.0)
        self.assertEqual(len(self.part.stage), 64)

    def test_reaped_part_gives_409_and_stays_queued(self):
        self.claim_part()
        AudiobookPart.objects.filter(pk=self.part.pk).update(lease_until=timezone.now() - timedelta(minutes=1))
        self.assertEqual(sched.reap_expired_leases()['requeued'], 1)
        response = self.call('post', self.part_url('heartbeat'), data={'progress': 0.5})
        self.assertEqual(response.status_code, 409)
        self.part.refresh_from_db()
        self.assertEqual((self.part.status, self.part.worker_id), ('queued', ''))

    def test_other_worker_is_409(self):
        self.claim_part()
        response = self.call('post', self.part_url('heartbeat'), data={'progress': 0.5}, worker_id=OTHER_WORKER)
        self.assertEqual(response.status_code, 409)


@override_settings(AUDIOBOOK_ENABLED=True)
class UploadTests(WorkerBase):
    def setUp(self):
        super().setUp()
        self.claim_part()

    def test_valid_upload_is_201_and_tagged(self):
        chapter = self.chapters[0]
        response = self.upload(chapter)
        self.assertEqual(response.status_code, 201)
        path = self.audio_path(chapter)
        self.assertTrue(os.path.exists(path))
        tags = OggOpus(path)
        self.assertEqual(tags['title'], ['Chapter 1'])
        self.assertEqual(tags['album'], ['Foo (Generated audiobook) — Part 1'])
        self.assertEqual(tags['tracknumber'], ['1'])
        self.assertEqual(tags['language'], ['en'])
        self.assertEqual(tags['comment'], [SITE_DISCLAIMER])
        self.part.refresh_from_db()
        upload = self.part.uploads[str(chapter.pk)]
        self.assertEqual(upload['sha256'], hashlib.sha256(self.fixtures['valid']).hexdigest())
        self.assertTrue(upload['file_path'].endswith(f'part-001/g1/{chapter.pk:05}.ogg'))
        self.assertGreater(upload['duration_s'], 10)

    def test_same_upload_again_is_200(self):
        chapter = self.chapters[0]
        self.assertEqual(self.upload(chapter).status_code, 201)
        self.assertEqual(self.upload(chapter).status_code, 200)

    def test_sha_mismatch_is_400_and_leaves_no_part_file(self):
        chapter = self.chapters[0]
        response = self.upload(chapter, sha256='0' * 64)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(list(Path(svc.audio_dir(self.source)).rglob('*.part')))
        self.assertFalse(os.path.exists(self.audio_path(chapter)))

    def test_each_invalid_fixture_is_400_with_a_reason(self):
        cases = [
            ('stereo', 'mono'),
            ('mp3', 'Ogg'),
            ('loud', 'kbps'),
            ('short', 'longer than 10 s'),
        ]
        chapter = self.chapters[0]
        for name, reason in cases:
            with self.subTest(fixture=name):
                response = self.upload(chapter, data=self.fixtures[name])
                self.assertEqual(response.status_code, 400)
                self.assertIn(reason, response.json()['detail'])
                self.assertFalse(list(Path(svc.audio_dir(self.source)).rglob('*.part')))
                self.assertFalse(os.path.exists(self.audio_path(chapter)))

    def test_too_big_is_413_and_leaves_no_part_file(self):
        chapter = self.chapters[0]
        with patch('lncrawler_api.views.audiobook_worker_views.MAX_UPLOAD_BYTES', 1000):
            response = self.upload(chapter)
        self.assertEqual(response.status_code, 413)
        self.assertFalse(list(Path(svc.audio_dir(self.source)).rglob('*.part')))

    def test_chapter_not_in_the_part_is_404(self):
        self.add_chapters(self.source, [300], first_id=3)
        other = Chapter.objects.get(novel_from_source=self.source, chapter_id=3)
        response = self.upload(other)
        self.assertEqual(response.status_code, 404)

    def test_other_worker_is_409(self):
        response = self.upload(self.chapters[0], key=self.other_key, worker_id=OTHER_WORKER)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(os.path.exists(self.audio_path(self.chapters[0])))


@override_settings(AUDIOBOOK_ENABLED=True)
class CompleteTests(WorkerBase):
    def setUp(self):
        super().setUp()
        self.claim_part()

    def upload_all(self):
        for chapter in self.chapters:
            self.assertIn(self.upload(chapter).status_code, (200, 201))

    def test_missing_chapter_is_400_with_the_ids(self):
        self.assertEqual(self.upload(self.chapters[0]).status_code, 201)
        response = self.call('post', self.part_url('complete'), data=self.complete_body())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['missing'], [self.chapters[1].pk])
        self.part.refresh_from_db()
        self.assertEqual(self.part.status, 'claimed')

    def test_bad_payload_is_400(self):
        body = self.complete_body()
        body['cast'] = []
        response = self.call('post', self.part_url('complete'), data=body)
        self.assertEqual(response.status_code, 400)

    def test_non_string_cast_description_is_400(self):
        body = self.complete_body()
        body['cast']['Narrator']['description'] = ['calm']
        response = self.call('post', self.part_url('complete'), data=body)
        self.assertEqual(response.status_code, 400)
        self.part.refresh_from_db()
        self.assertEqual(self.part.status, 'claimed')

    def test_success_records_chapters_totals_cast_and_credits(self):
        self.audiobook.cast = {'Old': {'engine': 'kokoro'}}
        self.audiobook.save()
        self.upload_all()
        response = self.call('post', self.part_url('complete'), data=self.complete_body())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'done'})

        rows = list(AudiobookChapter.objects.filter(part=self.part).order_by('chapter__chapter_id'))
        self.assertEqual([row.chapter_id for row in rows], [ch.pk for ch in self.chapters])
        self.assertEqual(rows[0].offset_s, 0)
        self.assertAlmostEqual(rows[1].offset_s, rows[0].duration_s)

        self.part.refresh_from_db()
        self.assertEqual(self.part.status, 'done')
        self.assertIsNotNone(self.part.completed_at)
        self.assertAlmostEqual(self.part.duration_s, rows[0].duration_s + rows[1].duration_s)
        self.assertEqual(self.part.size_bytes, sum(row.size_bytes for row in rows))
        self.assertEqual((self.part.engine, self.part.engine_version), ('castwright+kokoro', 'castwright@test kokoro-v1'))
        self.assertEqual(self.part.worker_id, '')
        self.assertTrue(self.part.qa_passed)
        self.assertTrue(self.part.is_listenable())

        self.audiobook.refresh_from_db()
        self.assertEqual(set(self.audiobook.cast), {'Old', 'Narrator'})
        self.assertEqual(self.audiobook.credits, {'engine': 'castwright+kokoro', 'engine_version': 'castwright@test kokoro-v1'})
        self.assertEqual(self.audiobook.parts_done, 1)
        self.assertAlmostEqual(self.audiobook.total_duration_s, self.part.duration_s)

    def test_is_listenable_follows_qa_and_approval(self):
        self.upload_all()
        self.call('post', self.part_url('complete'), data=self.complete_body(qa_passed=False))
        self.part.refresh_from_db()
        self.assertFalse(self.part.is_listenable())
        self.part.approved = True
        self.part.save()
        self.assertTrue(self.part.is_listenable())

    def test_regenerate_removes_the_old_generation_on_commit(self):
        self.upload_all()
        with self.captureOnCommitCallbacks(execute=True):
            self.call('post', self.part_url('complete'), data=self.complete_body())
        old_dir = Path(svc.audio_dir(self.source)) / 'part-001' / 'g1'
        self.assertTrue(old_dir.is_dir())

        svc.regenerate_part(AudiobookPart.objects.get(pk=self.part.pk))
        response = self.call('post', self.claim_url(), data={'worker_id': WORKER}, worker_id=None)
        self.assertEqual(response.status_code, 200)
        self.part.refresh_from_db()
        self.assertEqual(self.part.generation, 2)

        for chapter in self.chapters:
            response = self.upload(chapter)
            self.assertEqual(response.status_code, 201)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.call('post', self.part_url('complete'), data=self.complete_body()).status_code, 200)

        self.assertFalse(old_dir.exists())
        rows = AudiobookChapter.objects.filter(part=self.part)
        self.assertTrue(all('/g2/' in row.file_path for row in rows))
        for row in rows:
            self.assertTrue(os.path.exists(os.path.join(self.tmp, row.file_path)))


@override_settings(AUDIOBOOK_ENABLED=True)
class FailTests(WorkerBase):
    def setUp(self):
        super().setUp()
        self.claim_part()

    def fail(self, retryable, worker_id=WORKER):
        return self.call(
            'post', self.part_url('fail'), data={'error': 'boom', 'retryable': retryable}, worker_id=worker_id,
        )

    def test_retryable_below_max_is_requeued(self):
        response = self.fail(True)
        self.assertEqual(response.status_code, 200)
        self.part.refresh_from_db()
        self.assertEqual((self.part.status, self.part.attempts, self.part.error_message), ('queued', 1, 'boom'))
        self.assertEqual(self.part.worker_id, '')

    def test_at_max_attempts_it_fails(self):
        self.part.attempts = svc.MAX_ATTEMPTS - 1
        self.part.save()
        self.fail(True)
        self.part.refresh_from_db()
        self.assertEqual((self.part.status, self.part.attempts), ('failed', svc.MAX_ATTEMPTS))

    def test_not_retryable_fails(self):
        self.fail(False)
        self.part.refresh_from_db()
        self.assertEqual(self.part.status, 'failed')

    def test_other_worker_is_409(self):
        response = self.fail(True, worker_id=OTHER_WORKER)
        self.assertEqual(response.status_code, 409)
        self.part.refresh_from_db()
        self.assertEqual(self.part.status, 'claimed')


@override_settings(AUDIOBOOK_ENABLED=True)
class PingTests(WorkerBase):
    def test_ping_creates_then_updates_the_worker(self):
        body = {'worker_id': 'w9', 'version': '2', 'available': True, 'message': ''}
        response = self.call('post', reverse('audiobook_worker_ping'), data=body, worker_id=None)
        self.assertEqual(response.status_code, 200)
        worker = AudiobookWorker.objects.get(worker_id='w9')
        self.assertEqual((worker.version, worker.available), ('2', True))
        self.assertIsNotNone(worker.last_seen_at)
        self.assertEqual(worker.user.username, 'worker-a')

        body.update(available=False, message='busy')
        self.call('post', reverse('audiobook_worker_ping'), data=body, worker_id=None)
        self.assertEqual(AudiobookWorker.objects.filter(worker_id='w9').count(), 1)
        worker.refresh_from_db()
        self.assertEqual((worker.available, worker.message), (False, 'busy'))

    def test_ping_stores_the_languages_and_defaults_to_english(self):
        body = {'worker_id': 'w9', 'version': '2', 'languages': ['EN', 'fr']}
        self.call('post', reverse('audiobook_worker_ping'), data=body, worker_id=None)
        self.assertEqual(AudiobookWorker.objects.get(worker_id='w9').languages, ['en', 'fr'])

        del body['languages']
        self.call('post', reverse('audiobook_worker_ping'), data=body, worker_id=None)
        self.assertEqual(AudiobookWorker.objects.get(worker_id='w9').languages, ['en'])

    def test_ping_with_bad_languages_is_400_and_changes_nothing(self):
        body = {'worker_id': 'w9', 'version': '2', 'languages': 'en'}
        response = self.call('post', reverse('audiobook_worker_ping'), data=body, worker_id=None)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(AudiobookWorker.objects.filter(worker_id='w9').exists())


@override_settings(AUDIOBOOK_ENABLED=True)
class HousekeepingLeftoverTests(WorkerBase):
    """Leftovers of uploads are removed; the live generation and a claimed part's generation are kept."""

    def write(self, path, size=10):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as handle:
            handle.write(b'x' * size)
        return path

    def test_leftovers_are_removed_and_live_generations_kept(self):
        audio = Path(svc.audio_dir(self.source))
        part_dir = audio / 'part-001'
        live = self.write(str(part_dir / 'g1' / '00001.ogg'))
        self.write(str(part_dir / 'g2' / '00002.ogg'))  # the generation of the claimed part
        self.write(str(part_dir / 'g0' / '00001.ogg'))  # orphan
        self.write(str(part_dir / 'g3' / '00001.ogg'))  # orphan
        self.write(str(part_dir / 'g3' / '00002.ogg'))  # orphan
        old_part = self.write(str(part_dir / 'g1' / 'old.part'))
        fresh_part = self.write(str(part_dir / 'g1' / 'fresh.part'))
        self.write(str(part_dir / 'g4' / '00001.ogg'))  # orphan, but written just now: kept for an hour
        two_days = timezone.now().timestamp() - 2 * 24 * 3600
        os.utime(old_part, (two_days, two_days))
        for orphan in ('g0', 'g3'):
            os.utime(part_dir / orphan, (two_days, two_days))

        AudiobookChapter.objects.create(
            part=self.part, chapter=self.chapters[0],
            file_path=os.path.relpath(live, self.tmp), duration_s=1, size_bytes=10, sha256='x',
        )
        self.claim_part()
        self.part.generation = 2
        self.part.save()

        counts = sched.audiobook_housekeeping()

        self.assertEqual(counts['leftovers'], 1 + 1 + 2)  # old .part, g0 file, two g3 files
        self.assertFalse(os.path.exists(old_part))
        self.assertTrue(os.path.exists(fresh_part))
        self.assertTrue(os.path.isdir(part_dir / 'g1'))
        self.assertTrue(os.path.isdir(part_dir / 'g2'))
        self.assertFalse((part_dir / 'g0').exists())
        self.assertFalse((part_dir / 'g3').exists())
        self.assertTrue(os.path.isdir(part_dir / 'g4'))


class CreateWorkerCommandTests(TestCase):
    def test_create_is_idempotent_and_rotate_changes_the_token(self):
        out = StringIO()
        call_command('create_audiobook_worker', 'bot', stdout=out)
        first = Token.objects.get(user__username='bot').key
        self.assertIn(first, out.getvalue())

        call_command('create_audiobook_worker', 'bot', stdout=StringIO())
        self.assertEqual(Token.objects.get(user__username='bot').key, first)
        self.assertEqual(get_user_model().objects.filter(username='bot').count(), 1)

        user = get_user_model().objects.get(username='bot')
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.groups.filter(name=WORKER_GROUP).exists())

        call_command('create_audiobook_worker', 'bot', rotate=True, stdout=StringIO())
        second = Token.objects.get(user__username='bot').key
        self.assertNotEqual(first, second)
        self.assertFalse(Token.objects.filter(key=first).exists())

    def test_rerun_without_rotate_keeps_the_token_and_does_not_print_it(self):
        call_command('create_audiobook_worker', 'bot', stdout=StringIO())
        key = Token.objects.get(user__username='bot').key

        out = StringIO()
        call_command('create_audiobook_worker', 'bot', stdout=out)

        self.assertIn('token unchanged', out.getvalue())
        self.assertNotIn('Token:', out.getvalue())
        self.assertNotIn(key, out.getvalue())
        self.assertEqual(Token.objects.get(user__username='bot').key, key)


class FakeWorkerGuardTests(TestCase):
    def test_create_user_needs_a_local_url(self):
        with self.assertRaisesMessage(CommandError, 'local --url'):
            call_command('audiobook_fake_worker', url='https://staging.example.org', create_user='fakeworker')
        self.assertFalse(get_user_model().objects.filter(username='fakeworker').exists())


@override_settings(AUDIOBOOK_ENABLED=True)
class FakeWorkerTests(StaticLiveServerTestCase):
    """The fake worker against the live API: one part, two chapters, playable files on disk."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='fake-worker-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        output = override_settings(LNCRAWL_OUTPUT_PATH=self.tmp)
        output.enable()
        self.addCleanup(output.disable)

        novel = make_novel('Foo', 'foo')
        source = make_source_row(novel)
        source.source_path = os.path.join('foo', 'site')
        source.save()
        source_dir = source.absolute_source_path
        os.makedirs(source_dir, exist_ok=True)
        self.chapters = []
        for number in (1, 2):
            write_chapter(source_dir, number, body_size=1500)
            self.chapters.append(Chapter.objects.create(
                novel_from_source=source, chapter_id=number, url=f'http://foo/{number}',
                title=f'Chapter {number}', has_content=True, word_count=300,
            ))
        self.audiobook = Audiobook.objects.create(novel=novel, source=source)
        self.part = AudiobookPart.objects.create(
            audiobook=self.audiobook, index=1, chapter_start=1, chapter_end=2, word_count=600,
            chapter_ids=[ch.pk for ch in self.chapters],
        )

    def test_fake_worker_completes_a_part(self):
        out = StringIO()
        call_command(
            'audiobook_fake_worker', url=self.live_server_url, create_user='fakeworker',
            parts=1, speedup=600, stdout=out,
        )
        self.part.refresh_from_db()
        self.assertEqual(self.part.status, 'done')
        rows = AudiobookChapter.objects.filter(part=self.part).order_by('chapter__chapter_id')
        self.assertEqual(rows.count(), 2)
        for row in rows:
            path = os.path.join(self.tmp, row.file_path)
            self.assertTrue(os.path.exists(path))
            duration, _info = audiobook_media.validate_audio(path)
            self.assertGreater(duration, 10)
        self.assertIn('Processed 1 part(s).', out.getvalue())


@override_settings(AUDIOBOOK_ENABLED=True)
class OwnershipTests(WorkerBase):
    """A worker id belongs to the account that first used it. Another account gets 403 on claim and ping,
    and 409 on every call that acts on a part held under that id."""

    def setUp(self):
        super().setUp()
        self.claim_part()
        self.call('post', self.claim_url(), data=self.claim_body())  # registers WORKER under worker-a

    def test_owner_still_works(self):
        response = self.call('post', self.part_url('heartbeat'), data={'progress': 0.5})
        self.assertEqual(response.status_code, 200)

    def test_claim_with_another_accounts_worker_id_is_403(self):
        response = self.call('post', self.claim_url(), data=self.claim_body(), key=self.other_key)
        self.assertEqual(response.status_code, 403)

    def test_ping_with_another_accounts_worker_id_is_403_and_keeps_the_owner(self):
        body = {'worker_id': WORKER, 'available': False}
        response = self.call('post', reverse('audiobook_worker_ping'), data=body, key=self.other_key, worker_id=None)
        self.assertEqual(response.status_code, 403)
        worker = AudiobookWorker.objects.get(worker_id=WORKER)
        self.assertEqual(worker.user.username, 'worker-a')
        self.assertTrue(worker.available)

    def test_calls_on_the_part_from_another_account_are_409(self):
        calls = [
            ('get', self.part_url('epub'), None),
            ('post', self.part_url('heartbeat'), {'progress': 0.5}),
            ('post', self.part_url('complete'), self.complete_body()),
            ('post', self.part_url('fail'), {'error': 'x', 'retryable': True}),
        ]
        for method, url, data in calls:
            with self.subTest(url=url):
                response = self.call(method, url, data=data, key=self.other_key)
                self.assertEqual(response.status_code, 409)
        response = self.upload(self.chapters[0], key=self.other_key)
        self.assertEqual(response.status_code, 409)
        self.part.refresh_from_db()
        self.assertEqual((self.part.status, self.part.worker_id, self.part.uploads), ('claimed', WORKER, {}))

    def test_complete_and_fail_from_another_worker_id_are_409(self):
        self.assertEqual(self.call('post', self.part_url('complete'), data=self.complete_body(), worker_id=OTHER_WORKER).status_code, 409)
        self.assertEqual(self.call('post', self.part_url('fail'), data={'error': 'x', 'retryable': False}, worker_id=OTHER_WORKER).status_code, 409)
        self.part.refresh_from_db()
        self.assertEqual(self.part.status, 'claimed')


@override_settings(AUDIOBOOK_ENABLED=True)
class RequestShapeTests(WorkerBase):
    """Bodies must be JSON objects, flags must be JSON booleans, progress must be a finite number."""

    def setUp(self):
        super().setUp()
        self.claim_part()

    def test_non_object_json_is_400_on_every_json_endpoint(self):
        calls = [
            ('post', self.claim_url(), None),
            ('post', self.part_url('heartbeat'), None),
            ('post', self.part_url('complete'), None),
            ('post', self.part_url('fail'), None),
            ('post', reverse('audiobook_worker_ping'), None),
        ]
        for method, url, _ in calls:
            with self.subTest(url=url):
                response = self.call(method, url, data=[1], worker_id=None if 'ping' in url else WORKER)
                self.assertEqual(response.status_code, 400)
        self.part.refresh_from_db()
        self.assertEqual((self.part.status, self.part.worker_id), ('claimed', WORKER))

    def test_progress_must_be_a_finite_number(self):
        for progress in ('abc', '0.5', True, float('nan')):
            with self.subTest(progress=progress):
                response = self.call('post', self.part_url('heartbeat'), data={'progress': progress})
                self.assertEqual(response.status_code, 400)
        self.part.refresh_from_db()
        self.assertEqual(self.part.progress, 0)

    def test_retryable_must_be_a_boolean(self):
        response = self.call('post', self.part_url('fail'), data={'error': 'x', 'retryable': 'yes'})
        self.assertEqual(response.status_code, 400)
        self.part.refresh_from_db()
        self.assertEqual(self.part.status, 'claimed')

    def test_available_must_be_a_boolean(self):
        body = {'worker_id': WORKER, 'available': 'no'}
        response = self.call('post', reverse('audiobook_worker_ping'), data=body, worker_id=None)
        self.assertEqual(response.status_code, 400)


@override_settings(AUDIOBOOK_ENABLED=True)
class UploadGuardTests(WorkerBase):
    def setUp(self):
        super().setUp()
        self.claim_part()

    def assertNothingStored(self, chapter):
        self.assertFalse(os.path.exists(self.audio_path(chapter)))
        self.assertFalse(list(Path(svc.audio_dir(self.source)).rglob('*.part')))
        self.part.refresh_from_db()
        self.assertEqual(self.part.uploads, {})

    def test_tagging_error_is_400_and_leaves_no_file(self):
        chapter = self.chapters[0]
        with patch('lncrawler_api.services.audiobook_media.tag_chapter_file', side_effect=OSError('disk gone')):
            response = self.upload(chapter)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['detail'], 'could not tag file: disk gone')
        self.assertNothingStored(chapter)

    def test_reclaim_during_processing_is_409_and_nothing_lands(self):
        chapter = self.chapters[0]
        real_validate = audiobook_media.validate_audio

        def reclaim_then_validate(path):
            AudiobookPart.objects.filter(pk=self.part.pk).update(generation=2)
            return real_validate(path)

        with patch('lncrawler_api.services.audiobook_media.validate_audio', side_effect=reclaim_then_validate):
            response = self.upload(chapter)
        self.assertEqual(response.status_code, 409)
        self.assertNothingStored(chapter)
        self.assertFalse(os.path.exists(self.audio_path(chapter, generation=2)))

    def test_size_bytes_is_the_size_after_tagging(self):
        chapter = self.chapters[0]

        def tag_and_grow(path, *_args, **_tags):
            with open(path, 'ab') as handle:
                handle.write(b'x' * 50)

        with patch('lncrawler_api.services.audiobook_media.tag_chapter_file', side_effect=tag_and_grow):
            response = self.upload(chapter)
        self.assertEqual(response.status_code, 201)
        self.part.refresh_from_db()
        upload = self.part.uploads[str(chapter.pk)]
        self.assertEqual(upload['size_bytes'], os.path.getsize(self.audio_path(chapter)))
        self.assertEqual(upload['size_bytes'], len(self.fixtures['valid']) + 50)

    def test_streaming_past_the_cap_is_413_without_content_length(self):
        # Django bounds the stream by Content-Length, so the streaming cap is checked on the stream directly
        chapter = self.chapters[0]
        data = self.fixtures['valid']
        final = Path(self.audio_path(chapter))
        final.parent.mkdir(parents=True, exist_ok=True)
        fd, partial_path = tempfile.mkstemp(dir=final.parent, suffix='.ogg.part')
        os.close(fd)
        request = SimpleNamespace(
            user=get_user_model().objects.get(username='worker-a'), stream=io.BytesIO(data),
        )
        with patch('lncrawler_api.views.audiobook_worker_views.MAX_UPLOAD_BYTES', 1000):
            response = views._store_upload(
                request, self.part, WORKER, chapter.pk, hashlib.sha256(data).hexdigest(), final, partial_path,
            )
        os.remove(partial_path)
        self.assertEqual(response.status_code, 413)
        self.assertNothingStored(chapter)
