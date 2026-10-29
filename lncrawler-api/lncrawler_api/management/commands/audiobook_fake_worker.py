"""
Fake audiobook worker: speaks the real worker HTTP API with generated silence-and-tone audio.

A dev and testing tool. It claims parts, downloads their EPUB, uploads contract-valid Ogg/Opus chapter
files made by ffmpeg, then completes or fails the part. Point --url at a staging server to use it there.
"""

import hashlib
import os
import subprocess
import tempfile
from urllib.parse import urlparse

import requests
from django.core.management.base import BaseCommand, CommandError

from ...services.audiobook_worker_auth import ensure_worker_token
from ...services.audiobook_service import WORDS_PER_MINUTE

CONTRACT_VERSION = '1'
MIN_CHAPTER_S = 12  # shortest generated chapter file, in seconds
FFMPEG_TIMEOUT = 300  # seconds allowed for one chapter encode
HTTP_TIMEOUT = 120  # seconds allowed for one call to the API
LOCAL_HOSTS = ('127.0.0.1', 'localhost')


class Command(BaseCommand):
    help = "Fake audiobook worker: claims parts and uploads generated audio through the worker API."

    def add_arguments(self, parser):
        parser.add_argument('--url', default='http://127.0.0.1:8000', help="Base URL of the API")
        parser.add_argument('--token', default='', help="Worker token")
        parser.add_argument(
            '--create-user', default='',
            help=(
                "Create (or reuse) this worker user in the local database and use its token, instead of --token. "
                "Only with a local --url: a remote server never gets the user"
            ),
        )
        parser.add_argument('--worker-id', default='fake-1', help="Worker id sent with every call")
        parser.add_argument('--parts', type=int, default=1, help="Parts to process before exiting; 0 = until claim returns 204")
        parser.add_argument('--speedup', type=float, default=30, help="Audio duration is the speech duration divided by this")
        parser.add_argument('--fail-qa', action='store_true', help="Report qa.passed = false")
        parser.add_argument('--fail', action='store_true', help="Call fail instead of uploading")

    def handle(self, *args, **options):
        if options['speedup'] <= 0:
            raise CommandError("--speedup must be positive")
        token = options['token']
        if options['create_user']:
            if urlparse(options['url']).hostname not in LOCAL_HOSTS:
                raise CommandError("--create-user writes to the local database: it needs a local --url, use --token otherwise")
            token, _ = ensure_worker_token(options['create_user'])
        if not token:
            raise CommandError("Give --token or --create-user")

        self.base = options['url'].rstrip('/') + '/api/audiobook-worker/'
        self.worker_id = options['worker_id']
        self.speedup = options['speedup']
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Token {token}',
            'X-Worker-Contract': CONTRACT_VERSION,
        })

        done = 0
        while options['parts'] == 0 or done < options['parts']:
            claim = self._claim()
            if claim is None:
                self.stdout.write("No part to claim, exiting.")
                break
            self._process(claim, options)
            done += 1
        self.stdout.write(f"Processed {done} part(s).")

    def _request(self, method, path, expected, what, **kwargs):
        response = self.session.request(
            method, self.base + path, timeout=HTTP_TIMEOUT,
            headers={'X-Worker-Id': self.worker_id, **kwargs.pop('headers', {})}, **kwargs,
        )
        if response.status_code not in expected:
            raise CommandError(f"{what} failed: HTTP {response.status_code} {response.text[:500]}")
        self.stdout.write(f"{what}: HTTP {response.status_code}")
        return response

    def _claim(self):
        response = self.session.post(
            self.base + 'claim', timeout=HTTP_TIMEOUT,
            json={'worker_id': self.worker_id, 'version': 'fake-worker'},
        )
        if response.status_code == 204:
            return None
        if response.status_code != 200:
            raise CommandError(f"claim failed: HTTP {response.status_code} {response.text[:500]}")
        claim = response.json()
        self.stdout.write(f"Claimed part {claim['part']['index']} of {claim['series']['title']} ({len(claim['chapters'])} chapters)")
        return claim

    def _process(self, claim, options):
        part_id = claim['part_id']
        epub = self._request('GET', f'parts/{part_id}/epub', {200}, "Downloaded EPUB")
        if not epub.content.startswith(b'PK'):
            raise CommandError("The EPUB is not a zip file")

        if options['fail']:
            self._request(
                'POST', f'parts/{part_id}/fail', {200}, "Failed part",
                json={'error': 'fake worker failure', 'retryable': True},
            )
            return

        chapters = claim['chapters']
        for number, chapter in enumerate(chapters, 1):
            duration = max(MIN_CHAPTER_S, chapter['word_count'] / WORDS_PER_MINUTE * 60 / self.speedup)
            data = self._encode(duration)
            sha256 = hashlib.sha256(data).hexdigest()
            self._request(
                'PUT', f"parts/{part_id}/chapters/{chapter['chapter_id']}", {200, 201},
                f"Uploaded chapter {number}/{len(chapters)}",
                data=data, headers={'Content-Type': 'audio/ogg', 'X-Content-SHA256': sha256},
            )
            self._request(
                'POST', f'parts/{part_id}/heartbeat', {200},
                f"Heartbeat {number}/{len(chapters)}",
                json={'progress': number / len(chapters), 'stage': 'uploading', 'message': 'fake worker'},
            )

        cast = {
            'Narrator': {'engine': 'fake', 'voice': 'fake-narrator', 'role': 'narrator'},
            'Fake Hero': {'engine': 'fake', 'voice': 'fake-hero', 'role': 'main'},
            'Fake Villain': {'engine': 'fake', 'voice': 'fake-villain', 'role': 'minor'},
        }
        qa = {
            'passed': not options['fail_qa'],
            'checks': {'fake': {'value': 1, 'threshold': 1, 'passed': not options['fail_qa']}},
            'notes': 'generated by audiobook_fake_worker',
        }
        self._request(
            'POST', f'parts/{part_id}/complete', {200},
            "Completed part",
            json={
                'cast': cast,
                'qa': qa,
                'engine': 'fake+sine',
                'engine_version': 'audiobook_fake_worker 1',
            },
        )

    def _encode(self, duration):
        """A contract-valid chapter file of the given length, as bytes: a tone mixed with silence."""
        with tempfile.TemporaryDirectory(prefix='audiobook-fake-') as tmp:
            path = os.path.join(tmp, 'chapter.ogg')
            command = [
                'ffmpeg', '-v', 'error', '-y',
                '-f', 'lavfi', '-i', 'sine=frequency=220:sample_rate=48000',
                '-f', 'lavfi', '-i', 'anullsrc=channel_layout=mono:sample_rate=48000',
                '-filter_complex', '[0:a][1:a]amix=inputs=2:duration=first',
                '-t', f'{duration:.2f}', '-ac', '1', '-ar', '48000',
                '-c:a', 'libopus', '-b:a', '24k', '-vbr', 'on', path,
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT)
            if result.returncode != 0:
                raise CommandError(f"ffmpeg failed: {result.stderr[:500]}")
            with open(path, 'rb') as f:
                return f.read()
