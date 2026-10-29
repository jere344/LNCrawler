"""Checks and tags of the chapter audio files that workers upload.

Prod checks every upload with ffprobe against the audio format of the worker contract, and writes
the metadata itself with mutagen. Nothing here encodes audio.
"""
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile

from django.conf import settings
from django.db.models import Q, Sum
from mutagen.oggopus import OggOpus

from ..models import AudiobookChapter, AudiobookPart
from . import audiobook_service as svc
from .audiobook_service import MAX_BITRATE_KBPS
from .epub_service import _build_lock

logger = logging.getLogger("lncrawler_api.audiobooks")

PROBE_TIMEOUT = 60  # seconds allowed for one ffprobe run
MIN_DURATION_S = 10  # a chapter file must be longer than this
DURATION_TOLERANCE = 0.01  # stream and container durations must agree within 1 %
RETAG_NAME = '.retag'  # lock file of retagging, in audio/: audio/.retag.lock


class AudioRejected(Exception):
    """An uploaded file does not follow the audio format. ``reason`` tells the worker why."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _probe(path):
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', str(path)],
            capture_output=True, text=True, timeout=PROBE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise AudioRejected("ffprobe timed out reading the file")
    except OSError:
        logger.exception("ffprobe could not run")
        raise AudioRejected("the server could not read the file")
    if result.returncode != 0:
        raise AudioRejected("the file is not readable audio")
    try:
        return json.loads(result.stdout or '{}')
    except ValueError:
        raise AudioRejected("the file is not readable audio")


def validate_audio(path):
    """Check an uploaded chapter file against the contract. Returns (duration_s, info), or raises AudioRejected."""
    info = _probe(path)
    fmt = info.get('format') or {}
    streams = info.get('streams') or []

    if 'ogg' not in (fmt.get('format_name') or '').split(','):
        raise AudioRejected("the container must be Ogg")
    audio = [s for s in streams if s.get('codec_type') == 'audio']
    if len(audio) != 1:
        raise AudioRejected("the file must hold exactly one audio stream")
    stream = audio[0]
    if stream.get('codec_name') != 'opus':
        raise AudioRejected("the codec must be Opus")
    if stream.get('channels') != 1:
        raise AudioRejected("the audio must be mono")
    if str(stream.get('sample_rate')) != '48000':
        raise AudioRejected("the sample rate must be 48 kHz")

    try:
        duration_s = float(fmt.get('duration'))
    except (TypeError, ValueError):
        raise AudioRejected("the duration is missing")
    if duration_s <= MIN_DURATION_S:
        raise AudioRejected(f"the chapter must be longer than {MIN_DURATION_S} s")

    try:
        bit_rate = float(fmt['bit_rate']) if fmt.get('bit_rate') else int(fmt.get('size', 0)) * 8 / duration_s
    except (TypeError, ValueError):
        raise AudioRejected("the bitrate cannot be read")
    if bit_rate > MAX_BITRATE_KBPS * 1000:
        raise AudioRejected(f"the bitrate must be at most {MAX_BITRATE_KBPS} kbps on average")

    stream_duration = stream.get('duration')
    if stream_duration is not None:
        try:
            stream_duration = float(stream_duration)
        except (TypeError, ValueError):
            raise AudioRejected("the stream duration cannot be read")
        if abs(stream_duration - duration_s) > DURATION_TOLERANCE * duration_s:
            raise AudioRejected("the stream duration must match the container duration within 1 %")

    return duration_s, info


def audiobook_metadata(audiobook):
    """The metadata written into the tags of the chapter files and of the .m4b files."""
    source = audiobook.source
    latest = audiobook.parts.filter(status='done').order_by('-completed_at', '-index').first()
    listenable = audiobook.parts.filter(status__in=['done', 'stale']).filter(Q(qa_passed=True) | Q(approved=True))
    return {
        'title': audiobook.novel.title,
        'authors': [author.name for author in source.authors.order_by('name')],
        'year': source.novel.created_at.year,
        'synopsis': source.synopsis or '',
        'language': audiobook.language,
        'parts_total': listenable.count() or audiobook.parts.count(),
        'narrator': "Generated voices (LNCrawler)",
        'disclaimer': (
            f"Generated audiobook made from the {source.external_source.source_name} text with generated voices. "
            "Not an official audiobook."
        ),
    }


def compute_tags_hash(audiobook):
    """sha256 of the metadata, the (index, engine) of each part and the (chapter_id, title) of each chapter row.
    Only database reads: no file is opened."""
    rows = list(
        AudiobookChapter.objects.filter(part__audiobook=audiobook)
        .order_by('part__index', 'chapter__chapter_id')
        .values_list('part__index', 'part__engine', 'chapter__chapter_id', 'chapter__title')
    )
    payload = json.dumps(
        {'metadata': audiobook_metadata(audiobook), 'rows': [list(row) for row in rows]},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def tag_chapter_file(path, metadata, part, chapter):
    """Write the Vorbis comments of a chapter file with mutagen, from the audiobook metadata."""
    audio = OggOpus(path)
    audio['title'] = [chapter.title or f"Chapter {chapter.chapter_id}"]
    audio['album'] = [f"{metadata['title']} (Generated audiobook) \u2014 Part {part.index}"]
    audio['artist'] = [", ".join(metadata['authors'])]
    audio['tracknumber'] = [str(chapter.chapter_id)]
    audio['language'] = [metadata['language']]
    audio['comment'] = [metadata['disclaimer']]
    audio['description'] = [metadata['disclaimer']]
    audio.save()


def retag_lock(audiobook):
    """Exclusive lock of an audiobook's files: held while retagging, and by an .m4b build while it reads them."""
    return _build_lock(os.path.join(svc.audio_dir(audiobook.source), RETAG_NAME))


def _retag_file(path, metadata, part, chapter):
    """Tag a copy of a chapter file and move it over the original, so a failure leaves the original intact."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix='.retag-', suffix='.ogg')
    os.close(fd)
    try:
        shutil.copy2(path, tmp)
        tag_chapter_file(tmp, metadata, part, chapter)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def retag_audiobook(audiobook):
    """Rewrite the tags of every chapter file, refresh the sizes and store the tags hash. Returns the files retagged.
    A missing file is logged and skipped."""
    metadata = audiobook_metadata(audiobook)
    count = 0
    rows = AudiobookChapter.objects.filter(part__audiobook=audiobook).select_related('part', 'chapter')
    for row in rows:
        path = os.path.join(settings.LNCRAWL_OUTPUT_PATH, row.file_path)
        if not os.path.isfile(path):
            logger.warning("Audio file of %s chapter %s missing, not retagged: %s", audiobook, row.chapter.chapter_id, path)
            continue
        _retag_file(path, metadata, row.part, row.chapter)
        row.size_bytes = os.path.getsize(path)
        row.save(update_fields=['size_bytes'])
        count += 1
    for part in audiobook.parts.annotate(chapter_bytes=Sum('chapters__size_bytes')).exclude(chapter_bytes=None):
        AudiobookPart.objects.filter(pk=part.pk).update(size_bytes=part.chapter_bytes)
    audiobook.refresh_totals()
    audiobook.tags_hash = compute_tags_hash(audiobook)
    audiobook.save(update_fields=['tags_hash', 'updated_at'])
    return count
