"""The API the audiobook workers call: claim a part, download its EPUB, upload the chapter audio,
then complete or fail it. The contract is in docs/audiobook-worker-contract.md.

Every call of a worker is authenticated with its token and checked against the part it holds: the
part must be claimed by the worker sending its id. Those checks are repeated under the row lock or
in a conditional UPDATE before any state changes, and the worker is never throttled.
"""
import hashlib
import logging
import math
import os
import shutil
import tempfile
from datetime import timedelta, timezone as dt_timezone
from functools import partial

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.http import FileResponse
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.response import Response

from ..models import Audiobook, AudiobookChapter, AudiobookPart, AudiobookWorker, Chapter
from ..services import audiobook_cover, audiobook_media, audiobook_service as svc, epub_service
from ..services.audiobook_media import AudioRejected
from ..services.audiobook_worker_auth import IsAudiobookWorker

logger = logging.getLogger("lncrawler_api.audiobooks")

MAX_UPLOAD_BYTES = 64 * 1024 * 1024  # largest chapter file a worker may upload
UPLOAD_CHUNK = 64 * 1024  # bytes read from the request per step
CLAIM_RETRY_DISABLED = 600  # Retry-After seconds when the feature is off
CLAIM_RETRY_IDLE = 300  # Retry-After seconds when no part can be claimed
CONTRACT_VERSION = '1'
LANGUAGES_MAX = 20  # most language codes a worker may announce in one request
PIN_RELEASE_DAYS = 7  # days without contact after which a worker's audiobooks may be claimed by another worker
WORKER_ID_MAX = 64
WORKER_VERSION_MAX = 64
STAGE_MAX = 64


def _iso(moment):
    return moment.astimezone(dt_timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _contract_error(request):
    """400 when the worker speaks another contract version than this API."""
    version = request.headers.get('X-Worker-Contract')
    if version is not None and version != CONTRACT_VERSION:
        return Response(
            {'detail': f"Unsupported worker contract {version}: this API speaks {CONTRACT_VERSION}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


def _worker_id(value):
    """The worker id, or None when it is missing or too long to be stored."""
    if not isinstance(value, str) or not value or len(value) > WORKER_ID_MAX:
        return None
    return value


def _header_worker_id(request):
    """(worker id, error response) for the calls that carry the X-Worker-Id header."""
    worker_id = _worker_id(request.headers.get('X-Worker-Id'))
    if worker_id is None:
        return None, Response({'detail': 'The X-Worker-Id header is required'}, status=status.HTTP_400_BAD_REQUEST)
    return worker_id, None


def _body_worker_id(data):
    """(worker id, error response) for claim and ping, which carry the id in the body."""
    worker_id = _worker_id(data.get('worker_id'))
    if worker_id is None:
        return None, Response({'detail': 'worker_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    return worker_id, None


def _json_body(request):
    """(body, error response): the body of a JSON call must be an object."""
    data = request.data
    if not isinstance(data, dict):
        return None, Response({'detail': 'The body must be a JSON object'}, status=status.HTTP_400_BAD_REQUEST)
    return data, None


def _number(value, default):
    """A finite number from a JSON value (``default`` when missing), or None when it is not one."""
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _flag(data, key, default):
    """The JSON boolean sent under ``key`` (``default`` when missing), or None when it is not one."""
    value = data.get(key, default)
    return value if isinstance(value, bool) else None


def _languages(data):
    """The languages the worker narrates, lower-cased, from ``languages`` (['en'] when missing). None when it is
    not a list of at most LANGUAGES_MAX strings."""
    value = data.get('languages')
    if value is None:
        return ['en']
    if not isinstance(value, list) or len(value) > LANGUAGES_MAX or not all(isinstance(v, str) for v in value):
        return None
    return list(dict.fromkeys(v.strip().lower() for v in value))


def _pin_free(prefix, worker_id, now):
    """Q of the audiobooks a worker may claim: not pinned, pinned to itself, or pinned to a worker not seen for
    PIN_RELEASE_DAYS. ``prefix`` is the path to the audiobook from the queried model ('audiobook__' or '')."""
    stale = AudiobookWorker.objects.filter(last_seen_at__lt=now - timedelta(days=PIN_RELEASE_DAYS)).values('worker_id')
    return Q(**{f'{prefix}worker_id__in': ['', worker_id]}) | Q(**{f'{prefix}worker_id__in': stale})


def _touch_worker(request, worker_id, **fields):
    """Record that a worker was seen now, with the fields it sent. False when another user owns the id."""
    values = {'last_seen_at': timezone.now(), 'user': request.user, **fields}
    try:
        with transaction.atomic():
            AudiobookWorker.objects.create(worker_id=worker_id, **values)
        return True
    except IntegrityError:
        # The id exists: only its owner, or a row not linked to any user yet, may be updated
        updated = (
            AudiobookWorker.objects.filter(worker_id=worker_id)
            .filter(Q(user__isnull=True) | Q(user=request.user))
            .update(**values)
        )
        return bool(updated)


def _forbidden():
    return Response(
        {'detail': 'The worker id belongs to another account'},
        status=status.HTTP_403_FORBIDDEN,
    )


def _conflict():
    return Response(
        {'detail': 'The part is not claimed by this worker: it was cancelled or reassigned'},
        status=status.HTTP_409_CONFLICT,
    )


def _owned_part_queryset(request, part_id, worker_id):
    """The part when it is claimed by this worker id, and the id belongs to the calling user."""
    owned = AudiobookWorker.objects.filter(worker_id=OuterRef('worker_id'), user=request.user)
    return AudiobookPart.objects.filter(pk=part_id, status='claimed', worker_id=worker_id).filter(Exists(owned))


def _no_work(retry_after):
    return Response(status=status.HTTP_204_NO_CONTENT, headers={'Retry-After': str(retry_after)})


def _series_title(source):
    return source.title or source.novel.title


def _authors(source):
    return [author.name for author in source.authors.all()]


def _claim_payload(request, part, audiobook):
    source = audiobook.source
    chapters = svc.part_chapters(part)
    return {
        'part_id': str(part.id),
        'audiobook_id': str(audiobook.id),
        'series': {
            'title': _series_title(source),
            'authors': _authors(source),
            'language': audiobook.language,
            'slug': source.novel.slug,
        },
        'part': {
            'index': part.index,
            'total_known': audiobook.parts.count(),
            'chapter_start': part.chapter_start,
            'chapter_end': part.chapter_end,
            'word_count': part.word_count,
        },
        'chapters': [
            {
                'chapter_id': ch.pk,
                'number': ch.chapter_id,
                'title': ch.title or f"Chapter {ch.chapter_id}",
                'word_count': ch.word_count or 0,
            }
            for ch in chapters
        ],
        'epub_url': request.build_absolute_uri(reverse('audiobook_worker_epub', args=[part.id])),
        'previous_cast': audiobook.cast,
        'lease_until': _iso(part.lease_until),
    }


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAudiobookWorker])
@throttle_classes([])
def claim(request):
    error = _contract_error(request)
    if error:
        return error
    data, error = _json_body(request)
    if error:
        return error
    worker_id, error = _body_worker_id(data)
    if error:
        return error
    languages = _languages(data)
    if languages is None:
        return Response({'detail': f'languages must be a list of at most {LANGUAGES_MAX} strings'}, status=400)
    version = str(data.get('version') or '')[:WORKER_VERSION_MAX]
    if not _touch_worker(request, worker_id, version=version, languages=languages):
        return _forbidden()

    if not settings.AUDIOBOOK_ENABLED:
        return _no_work(CLAIM_RETRY_DISABLED)

    now = timezone.now()
    with transaction.atomic():
        part = (
            AudiobookPart.objects.select_for_update(skip_locked=True, of=('self',))
            .select_related('audiobook__source__novel')
            .filter(
                status='queued',
                audiobook__status='active',
                audiobook__novel__is_dmca=False,
                audiobook__language__in=languages,
            )
            .filter(_pin_free('audiobook__', worker_id, now))
            .order_by('-priority', 'created_at')
            .first()
        )
        if part is None:
            return _no_work(CLAIM_RETRY_IDLE)
        audiobook = part.audiobook
        part.status = 'claimed'
        part.worker_id = worker_id
        part.claimed_at = now
        part.lease_until = now + timedelta(seconds=svc.LEASE_SECONDS)
        part.generation += 1
        part.uploads = {}
        part.progress = 0
        part.stage = ''
        part.save()
        # Conditional: another worker may have pinned the book since the filter above. Its part is then
        # rolled back, so this worker never holds a part of a book pinned to someone else.
        pinned = Audiobook.objects.filter(_pin_free('', worker_id, now), pk=audiobook.pk).update(worker_id=worker_id)
        if not pinned:
            transaction.set_rollback(True)
            return _no_work(CLAIM_RETRY_IDLE)

    return Response(_claim_payload(request, part, audiobook))


@api_view(['GET'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAudiobookWorker])
@throttle_classes([])
def part_epub(request, part_id):
    error = _contract_error(request)
    if error:
        return error
    worker_id, error = _header_worker_id(request)
    if error:
        return error
    _touch_worker(request, worker_id)

    part = _owned_part_queryset(request, part_id, worker_id).select_related('audiobook__source__novel').first()
    if part is None:
        return _conflict()
    source = part.audiobook.source
    chapters = svc.part_chapters(part)

    # The EPUB is built in a folder of its own. The open file keeps the data once the folder is removed.
    tmp_dir = tempfile.mkdtemp(prefix='audiobook-epub-')
    try:
        dest = os.path.join(tmp_dir, 'part.epub')
        epub_service._build(
            source, chapters, None, dest,
            series=(_series_title(source), part.index),
        )
        handle = open(dest, 'rb')
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return FileResponse(handle, content_type='application/epub+zip')


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAudiobookWorker])
@throttle_classes([])
def heartbeat(request, part_id):
    error = _contract_error(request)
    if error:
        return error
    worker_id, error = _header_worker_id(request)
    if error:
        return error
    _touch_worker(request, worker_id)

    data, error = _json_body(request)
    if error:
        return error
    number = _number(data.get('progress'), 0.0)
    if number is None:
        return Response({'detail': 'progress must be a number'}, status=status.HTTP_400_BAD_REQUEST)
    progress = min(1.0, max(0.0, number))
    lease_until = timezone.now() + timedelta(seconds=svc.LEASE_SECONDS)
    updated = _owned_part_queryset(request, part_id, worker_id).update(
        lease_until=lease_until,
        progress=progress,
        stage=str(data.get('stage') or '')[:STAGE_MAX],
    )
    if not updated:
        return _conflict()
    return Response({'lease_until': _iso(lease_until)})


def _discard(path):
    if os.path.exists(path):
        os.remove(path)


def _upload_file_path(source, part, chapter_pk):
    """Folder of the upload: each claim writes into its own generation folder."""
    return svc.audio_dir(source) / f'part-{part.index:03}' / f'g{part.generation}' / f'{chapter_pk:05}.ogg'


def _same_upload_exists(part, chapter_pk, sha256):
    """True when the chapter already has an upload of this hash whose file is still on disk."""
    upload = part.uploads.get(str(chapter_pk))
    return bool(
        upload
        and upload.get('sha256') == sha256
        and os.path.exists(os.path.join(settings.LNCRAWL_OUTPUT_PATH, upload['file_path']))
    )


@api_view(['PUT'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAudiobookWorker])
@throttle_classes([])
def chapter_upload(request, part_id, chapter_pk):
    error = _contract_error(request)
    if error:
        return error
    worker_id, error = _header_worker_id(request)
    if error:
        return error
    _touch_worker(request, worker_id)

    part = _owned_part_queryset(request, part_id, worker_id).select_related('audiobook__source__novel').first()
    if part is None:
        return _conflict()
    if chapter_pk not in part.chapter_ids:
        return Response({'detail': 'This chapter is not in the part'}, status=status.HTTP_404_NOT_FOUND)
    sha256 = (request.headers.get('X-Content-SHA256') or '').strip().lower()
    if not sha256:
        return Response({'detail': 'The X-Content-SHA256 header is required'}, status=status.HTTP_400_BAD_REQUEST)
    if _same_upload_exists(part, chapter_pk, sha256):
        return Response({'status': 'uploaded'})
    try:
        declared = int(request.META.get('CONTENT_LENGTH') or 0)
    except ValueError:
        declared = 0
    if declared > MAX_UPLOAD_BYTES:
        return Response({'detail': 'The file is too big'}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    source = part.audiobook.source
    final = _upload_file_path(source, part, chapter_pk)
    final.parent.mkdir(parents=True, exist_ok=True)
    # The body goes to a temporary file of the generation folder. It is removed on every exit path,
    # and only moved into place while the claim still holds.
    fd, partial_path = tempfile.mkstemp(dir=final.parent, suffix='.ogg.part')
    os.close(fd)
    os.chmod(partial_path, 0o644)
    try:
        return _store_upload(request, part, worker_id, chapter_pk, sha256, final, partial_path)
    finally:
        _discard(partial_path)


def _store_upload(request, part, worker_id, chapter_pk, sha256, final, partial_path):
    """Receive, check, tag and move one chapter file. The caller removes ``partial_path``."""
    audiobook = part.audiobook

    # Stream the body to the .part file, hashing it on the way
    hasher = hashlib.sha256()
    size = 0
    with open(partial_path, 'wb') as out:
        stream = request.stream
        while stream is not None:
            chunk = stream.read(UPLOAD_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                return Response({'detail': 'The file is too big'}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
            hasher.update(chunk)
            out.write(chunk)
    if hasher.hexdigest() != sha256:
        return Response({'detail': 'The SHA-256 of the file does not match the header'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        duration_s, _info = audiobook_media.validate_audio(partial_path)
    except AudioRejected as rejected:
        return Response({'detail': rejected.reason}, status=status.HTTP_400_BAD_REQUEST)

    chapter = Chapter.objects.select_related('novel_from_source').filter(pk=chapter_pk).first()
    if chapter is None:
        return Response({'detail': 'This chapter no longer exists'}, status=status.HTTP_404_NOT_FOUND)
    try:
        audiobook_media.tag_chapter_file(
            partial_path, audiobook_media.audiobook_metadata(audiobook), part, chapter,
        )
    except Exception as error:
        return Response({'detail': f"could not tag file: {error}"}, status=status.HTTP_400_BAD_REQUEST)
    size_bytes = os.path.getsize(partial_path)

    # Ownership is checked again under the row lock before the file is moved into place
    with transaction.atomic():
        current = (
            _owned_part_queryset(request, part.pk, worker_id)
            .filter(generation=part.generation)
            .select_for_update(of=('self',))
            .first()
        )
        if current is None:
            return _conflict()
        if _same_upload_exists(current, chapter_pk, sha256):
            return Response({'status': 'uploaded'})
        created = str(chapter_pk) not in current.uploads
        os.replace(partial_path, final)
        uploads = dict(current.uploads)
        uploads[str(chapter_pk)] = {
            'file_path': os.path.relpath(final, settings.LNCRAWL_OUTPUT_PATH),
            'sha256': sha256,
            'duration_s': duration_s,
            'size_bytes': size_bytes,
        }
        AudiobookPart.objects.filter(pk=current.pk).update(uploads=uploads)
    return Response({'status': 'uploaded'}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

def _remove_old_generations(part_dir, keep):
    for gen_dir in part_dir.glob('g*'):
        if gen_dir.is_dir() and gen_dir.name != keep:
            shutil.rmtree(gen_dir, ignore_errors=True)


def _build_cover_after_complete(audiobook_pk):
    """Build the cover once the part is committed. A failure is logged and never fails ``complete``."""
    try:
        audiobook = Audiobook.objects.select_related('novel', 'source').get(pk=audiobook_pk)
        if audiobook_cover.cover_is_stale(audiobook):
            audiobook_cover.build_cover(audiobook)
    except Exception:
        logger.exception("Could not build the cover of audiobook %s", audiobook_pk)


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAudiobookWorker])
@throttle_classes([])
def complete(request, part_id):
    error = _contract_error(request)
    if error:
        return error
    worker_id, error = _header_worker_id(request)
    if error:
        return error
    _touch_worker(request, worker_id)

    data, error = _json_body(request)
    if error:
        return error
    cast = data.get('cast')
    qa = data.get('qa')
    engine = data.get('engine')
    engine_version = data.get('engine_version')
    if not isinstance(cast, dict) or not isinstance(qa, dict):
        return Response({'detail': 'cast and qa must be objects'}, status=status.HTTP_400_BAD_REQUEST)
    if any(
        isinstance(entry, dict) and entry.get('description') is not None and not isinstance(entry['description'], str)
        for entry in cast.values()
    ):
        return Response({'detail': 'cast descriptions must be strings'}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(engine, str) or not engine.strip():
        return Response({'detail': 'engine must be a non-empty string'}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(engine_version, str):
        return Response({'detail': 'engine_version must be a string'}, status=status.HTTP_400_BAD_REQUEST)

    now = timezone.now()
    with transaction.atomic():
        part = (
            _owned_part_queryset(request, part_id, worker_id)
            .select_for_update(of=('self',))
            .select_related('audiobook__source__novel')
            .first()
        )
        if part is None:
            return _conflict()
        output_root = settings.LNCRAWL_OUTPUT_PATH
        missing = [
            pk for pk in part.chapter_ids
            if str(pk) not in part.uploads
            or not os.path.exists(os.path.join(output_root, part.uploads[str(pk)]['file_path']))
        ]
        if missing:
            return Response(
                {'detail': 'Some chapters have no uploaded audio', 'missing': missing},
                status=status.HTTP_400_BAD_REQUEST,
            )

        audiobook = Audiobook.objects.select_for_update().get(pk=part.audiobook_id)
        AudiobookChapter.objects.filter(part=part).delete()
        offset = 0.0
        total_size = 0
        rows = []
        for pk in part.chapter_ids:
            upload = part.uploads[str(pk)]
            rows.append(AudiobookChapter(
                part=part,
                chapter_id=pk,
                file_path=upload['file_path'],
                duration_s=upload['duration_s'],
                size_bytes=upload['size_bytes'],
                sha256=upload['sha256'],
                offset_s=offset,
            ))
            offset += upload['duration_s']
            total_size += upload['size_bytes']
        AudiobookChapter.objects.bulk_create(rows)

        AudiobookPart.objects.filter(pk=part.pk).update(
            status='done',
            completed_at=now,
            checked_at=now,
            duration_s=offset,
            size_bytes=total_size,
            engine=engine,
            engine_version=engine_version,
            cast=cast,
            qa=qa,
            qa_passed=bool(qa.get('passed')),
            worker_id='',
            claimed_at=None,
            lease_until=None,
            progress=1,
            attempts=0,
            error_message='',
        )
        audiobook.cast = {**audiobook.cast, **cast}
        audiobook.credits = {'engine': engine, 'engine_version': engine_version}
        audiobook.last_part_at = now
        audiobook.save(update_fields=['cast', 'credits', 'last_part_at', 'updated_at'])
        audiobook.refresh_totals()
        audiobook.tags_hash = audiobook_media.compute_tags_hash(audiobook)
        audiobook.save(update_fields=['tags_hash', 'updated_at'])

        part_dir = svc.audio_dir(part.audiobook.source) / f'part-{part.index:03}'
        transaction.on_commit(partial(_remove_old_generations, part_dir, f'g{part.generation}'))
        transaction.on_commit(partial(_build_cover_after_complete, audiobook.pk))
    return Response({'status': 'done'})


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAudiobookWorker])
@throttle_classes([])
def fail(request, part_id):
    error = _contract_error(request)
    if error:
        return error
    worker_id, error = _header_worker_id(request)
    if error:
        return error
    _touch_worker(request, worker_id)

    data, error = _json_body(request)
    if error:
        return error
    message = str(data.get('error') or '')[:2000]
    retryable = _flag(data, 'retryable', False)
    if retryable is None:
        return Response({'detail': 'retryable must be a boolean'}, status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        part = _owned_part_queryset(request, part_id, worker_id).select_for_update(of=('self',)).first()
        if part is None:
            return _conflict()
        attempts = part.attempts + 1
        new_status = 'queued' if retryable and attempts < svc.MAX_ATTEMPTS else 'failed'
        AudiobookPart.objects.filter(pk=part.pk).update(
            status=new_status,
            attempts=attempts,
            error_message=message,
            worker_id='',
            claimed_at=None,
            lease_until=None,
        )
    return Response({'status': new_status})


@api_view(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAudiobookWorker])
@throttle_classes([])
def ping(request):
    error = _contract_error(request)
    if error:
        return error
    data, error = _json_body(request)
    if error:
        return error
    worker_id, error = _body_worker_id(data)
    if error:
        return error
    languages = _languages(data)
    if languages is None:
        return Response({'detail': f'languages must be a list of at most {LANGUAGES_MAX} strings'}, status=400)
    available = _flag(data, 'available', True)
    if available is None:
        return Response({'detail': 'available must be a boolean'}, status=status.HTTP_400_BAD_REQUEST)
    if not _touch_worker(
        request, worker_id,
        version=str(data.get('version') or '')[:WORKER_VERSION_MAX],
        languages=languages,
        available=available,
        message=str(data.get('message') or ''),
    ):
        return _forbidden()
    return Response({'status': 'ok'})
