"""The .m4b files of an audiobook part: the chapter files of the part joined in one file, with chapter
marks, tags and the part cover.

A build runs ffmpeg (Opus is copied as is, AAC is encoded) and writes the tags with mutagen. The result is
kept in audio/cache/, under a name that changes with the part generation, the tags hash and the cover, so an
old file is never served after a new upload, a retag or a new cover.

Pruning: a file whose name no part uses any more is deleted once it is older than 10 minutes. A name that does
not parse (a stray *.tmp or *.lock, or an older naming scheme) is deleted only once it is older than a day.
"""
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time

from django.conf import settings
from django.db import IntegrityError, transaction
from mutagen.mp4 import MP4, MP4Cover

from ..models import Audiobook, AudiobookPart
from . import audiobook_cover, audiobook_media, audiobook_service as svc
from .epub_service import _build_lock

logger = logging.getLogger("lncrawler_api.audiobooks")

FORMATS = ('opus', 'aac')
CACHE_DIR = 'cache'  # folder of the .m4b files, inside audio/ of the source
FFMPEG_TIMEOUT = 2 * 60 * 60  # seconds allowed for one ffmpeg run
NICE_LEVEL = 10
PROTECTED_SECONDS = 10 * 60  # files modified this recently are never pruned
STRAY_TMP_SECONDS = 24 * 60 * 60  # a *.tmp older than this is left over from a crashed build
STDERR_TAIL = 800  # characters of ffmpeg stderr kept in the error
CACHE_NAME_RE = re.compile(r'part-(\d{3})-g(\d+)-(opus|aac)-([0-9a-f]{10})-([0-9a-f]{8})\.m4b')
MAX_NAME = 150  # longest download file name, extension included
AAC_BITRATE = '64k'


class M4bBuildError(RuntimeError):
    """An .m4b file could not be built. The message is shown to the admin."""


def _cache_dir(audiobook):
    return os.path.join(str(svc.audio_dir(audiobook.source)), CACHE_DIR)


def _name(index, generation, fmt, tags_hash, cover):
    return f"part-{index:03}-g{generation}-{fmt}-{tags_hash[:10]}-{cover}.m4b"


def _cache_name(part, fmt, cover):
    return _name(part.index, part.generation, fmt, part.audiobook.tags_hash, cover)


def _current_cover_key(audiobook):
    """Rebuild the cover when it is stale, then return its key, so a new source cover gives new .m4b names."""
    if audiobook_cover.cover_is_stale(audiobook):
        audiobook_cover.build_cover(audiobook)
    return audiobook_cover.cover_key(audiobook)


def _cache_path(part, fmt, rebuild_cover=True):
    audiobook = part.audiobook
    cover = _current_cover_key(audiobook) if rebuild_cover else audiobook_cover.cover_key(audiobook)
    return os.path.join(_cache_dir(audiobook), _cache_name(part, fmt, cover))


def cached_m4b(part, fmt, touch=True):
    """Path of the cached .m4b of a part in this format. None on a miss. It is touched, so it counts as recently
    used, unless touch is False. A lookup with touch=False is a plain read: it never rebuilds a stale cover."""
    path = _cache_path(part, fmt, rebuild_cover=touch)
    if not os.path.isfile(path):
        return None
    if touch:
        try:
            os.utime(path, None)
        except OSError as error:
            logger.warning("Could not touch %s: %s", path, error)
    return path if os.path.isfile(path) else None


def _escape_concat(path):
    """A file line of an ffmpeg concat list: the path in single quotes, each quote written as '\\''."""
    return "file '" + path.replace("'", "'\\''") + "'"


def _escape_meta(value):
    """Escape a value for an ffmetadata file: = ; # and backslash are escaped, newlines become spaces."""
    return re.sub(r'([=;#\\])', r'\\\1', value.replace('\r', ' ').replace('\n', ' '))


def _chapter_title(chapter):
    return chapter.title or f"Chapter {chapter.chapter_id}"


def _write_ffmpeg_inputs(list_path, meta_path, part, rows):
    """Write the concat list of the chapter files and the ffmetadata with one [CHAPTER] per chapter row."""
    with open(list_path, 'w', encoding='utf-8') as out:
        for row in rows:
            out.write(_escape_concat(os.path.join(settings.LNCRAWL_OUTPUT_PATH, row.file_path)) + '\n')
    with open(meta_path, 'w', encoding='utf-8') as out:
        out.write(';FFMETADATA1\n')
        for row in rows:
            start = int(round(row.offset_s * 1000))
            end = int(round((row.offset_s + row.duration_s) * 1000))
            out.write(
                '[CHAPTER]\nTIMEBASE=1/1000\n'
                f'START={start}\nEND={end}\n'
                f'title={_escape_meta(_chapter_title(row.chapter))}\n'
            )


def _ffmpeg_command(list_path, meta_path, fmt, output):
    command = [
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        '-f', 'concat', '-safe', '0', '-i', list_path,
        '-i', meta_path,
        # -map_metadata 1 takes the global tags from the ffmetadata file, which has none, so no tag of the
        # chapter files is copied; -1 would drop the chapter titles too.
        '-map', '0:a', '-map_metadata', '1', '-map_chapters', '1',
    ]
    if fmt == 'opus':
        command += ['-c:a', 'copy']
    else:
        command += ['-c:a', 'aac', '-b:a', AAC_BITRATE, '-ac', '1']
    command += ['-movflags', '+faststart', '-f', 'mp4', output]
    nice = shutil.which('nice')
    if nice:
        command = [nice, '-n', str(NICE_LEVEL)] + command
    return command


def _run_ffmpeg(command):
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, errors='replace', timeout=FFMPEG_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise M4bBuildError(f"ffmpeg did not finish within {FFMPEG_TIMEOUT // 3600} h")
    if result.returncode != 0:
        tail = (result.stderr or '').strip()[-STDERR_TAIL:]
        raise M4bBuildError(f"ffmpeg failed: {tail or 'no output'}")


def _tag_m4b(path, part, metadata):
    """Write the MP4 tags and the part cover into a built .m4b."""
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    title = metadata['title']
    authors = ", ".join(metadata['authors'])
    synopsis = metadata['synopsis']
    tags['\xa9nam'] = [
        f"{title} (Generated audiobook) — Part {part.index} (Ch. {part.chapter_start}–{part.chapter_end})"
    ]
    tags['\xa9alb'] = [f"{title} (Generated audiobook)"]
    tags['\xa9ART'] = [authors]
    tags['aART'] = [authors]
    tags['\xa9wrt'] = [metadata['narrator']]
    tags['\xa9gen'] = ['Audiobook']
    tags['\xa9day'] = [str(metadata['year'])]
    tags['\xa9cmt'] = [metadata['disclaimer']]
    tags['desc'] = [metadata['disclaimer'][:255]]
    tags['ldes'] = [f"{metadata['disclaimer']}\n\n{synopsis}" if synopsis else metadata['disclaimer']]
    tags['trkn'] = [(part.index, metadata['parts_total'])]
    tags['stik'] = [2]
    tags['\xa9grp'] = [title]
    tags['\xa9mvn'] = [title]
    tags['\xa9mvi'] = [part.index]
    tags['shwm'] = [1]
    tags['\xa9too'] = ['lncrawler']
    tags['----:com.apple.iTunes:LANGUAGE'] = [metadata['language'].encode('utf-8')]
    cover = audiobook_cover.part_cover_jpeg(part.audiobook, part.index)
    tags['covr'] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()


def build_m4b(part, fmt, progress=None):
    """Build the .m4b of a part in a format, store it in the cache and return its path.

    The part must be done or stale, passed QA or be approved, and have chapter rows. The tags are made current
    first. The chapter files are read under the retag lock, so a retag cannot rewrite them mid-build. A file built
    by another request while this one waited for the lock is returned as is.
    """
    if fmt not in FORMATS:
        raise ValueError(f"Unknown format: {fmt!r}")
    audiobook = part.audiobook
    if not part.is_listenable() or not part.chapters.exists():
        raise ValueError("This part has no listenable audio yet.")
    os.makedirs(_cache_dir(audiobook), exist_ok=True)
    with audiobook_media.retag_lock(audiobook):
        if audiobook.tags_hash != audiobook_media.compute_tags_hash(audiobook):
            audiobook_media.retag_audiobook(audiobook)

        dest = _cache_path(part, fmt)
        with _build_lock(dest):
            cached = cached_m4b(part, fmt)
            if cached is not None:
                return cached

            rows = list(part.chapters.select_related('chapter').order_by('offset_s'))
            metadata = audiobook_media.audiobook_metadata(audiobook)
            tmp = dest + '.tmp'
            logger.info("Building %s for part %s of %s", os.path.basename(dest), part.index, audiobook)
            with tempfile.TemporaryDirectory(prefix='m4b-', dir=_cache_dir(audiobook)) as work:
                list_path = os.path.join(work, 'list.txt')
                meta_path = os.path.join(work, 'meta.txt')
                _write_ffmpeg_inputs(list_path, meta_path, part, rows)
                if progress:
                    progress(0, len(rows))
                try:
                    _run_ffmpeg(_ffmpeg_command(list_path, meta_path, fmt, tmp))
                    _tag_m4b(tmp, part, metadata)
                    os.replace(tmp, dest)
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)
            if progress:
                progress(len(rows), len(rows))
    try:
        prune_m4b_cache(keep=dest)
    except Exception:
        logger.exception("Could not prune the .m4b cache after building %s", os.path.basename(dest))
    return dest


def download_filename(part):
    """Name of the file offered to the user, the same for both formats."""
    name = f"{part.audiobook.novel.title} - Part {part.index:02} (Ch. {part.chapter_start}-{part.chapter_end})"
    name = re.sub(r'[^\w \-()._]', '', name)
    name = re.sub(r' +', ' ', name).strip()
    label = ' [generated]'  # added after the cleanup, which would drop the brackets
    return name[:MAX_NAME - len('.m4b') - len(label)].rstrip() + label + '.m4b'


def m4b_job_key(part_id, fmt):
    """Job.query value identifying one .m4b build: m4b:<part id>:<format>."""
    return f"m4b:{part_id}:{fmt}"


def parse_m4b_job_key(key):
    """Inverse of m4b_job_key. Returns (part id, format)."""
    parts = str(key or "").split(":")
    if len(parts) != 3 or parts[0] != "m4b" or parts[2] not in FORMATS:
        raise ValueError(f"Invalid m4b job key: {key!r}")
    return parts[1], parts[2]


def _active_m4b_job(key):
    from ..models import Job

    return Job.objects.filter(
        job_type=Job.JOB_TYPE_M4B,
        query=key,
        status__in=[Job.STATUS_CREATED, Job.STATUS_DOWNLOADING],
    ).first()


def active_m4b_job(part, fmt):
    """The queued or running job building this .m4b, or None."""
    return _active_m4b_job(m4b_job_key(part.pk, fmt))


def enqueue_m4b_job(part, fmt, user=None):
    """Return the active job for this .m4b, creating one if none is running."""
    from ..models import Job

    key = m4b_job_key(part.pk, fmt)
    existing = _active_m4b_job(key)
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            return Job.objects.create(
                job_type=Job.JOB_TYPE_M4B,
                status=Job.STATUS_CREATED,
                query=key,
                user=user,
                progress_unit="chapters",
            )
    except IntegrityError:
        # A concurrent request created the active job first; the partial
        # unique constraint rejected ours. If that job has already finished,
        # reuse the most recent job of this key instead.
        existing = _active_m4b_job(key) or Job.objects.filter(
            job_type=Job.JOB_TYPE_M4B, query=key,
        ).order_by('-created_at').first()
        if existing is None:
            raise
        return existing


def run_m4b_job(job_id, payload):
    """Supervisor entry point: build the .m4b described by payload's job key."""
    from ..models import Job

    job = Job.objects.filter(id=job_id).first()
    if job is None:
        logger.error("M4B job %s not found", job_id)
        return
    try:
        part_id, fmt = parse_m4b_job_key(payload)
        part = AudiobookPart.objects.select_related('audiobook__novel', 'audiobook__source').get(pk=part_id)
        job.update_status(Job.STATUS_DOWNLOADING)
        path = build_m4b(
            part, fmt,
            progress=lambda done, total: job.update_progress(done, total, "chapters"),
        )
        job.update_download_results(path, [download_filename(part)])
        job.update_status(Job.STATUS_DOWNLOAD_COMPLETED)
    except Exception as e:
        # Deterministic failures (bad key, missing part, no audio, ffmpeg errors) are
        # recorded on the job rather than re-raised, so the supervisor does not
        # retry them forever.
        logger.warning("M4B job %s failed: %s", job_id, e, exc_info=True)
        job.update_status(Job.STATUS_FAILED, str(e) or "M4B build failed")


def _cache_dirs():
    """(audiobook, folder) of each audio/cache folder of an audiobook with chapter rows, inside LNCRAWL_OUTPUT_PATH."""
    audiobooks = Audiobook.objects.filter(parts__chapters__isnull=False).distinct().select_related('source')
    found = []
    for audiobook in audiobooks:
        folder = _cache_dir(audiobook)
        if os.path.isdir(folder) and svc.is_inside_output_path(folder):
            found.append((audiobook, folder))
    return found


def _current_names(audiobook):
    """The .m4b names the parts of an audiobook have now: one per part and format, with the current tags hash and
    cover key. Empty when the cover has no stamp."""
    cover = audiobook_cover.cover_key(audiobook)
    if cover is None:
        return set()
    return {
        _name(index, generation, fmt, audiobook.tags_hash, cover)
        for index, generation in audiobook.parts.values_list('index', 'generation')
        for fmt in FORMATS
    }


def m4b_cache_bytes():
    """Total size of the .m4b files in the caches."""
    total = 0
    for _audiobook, folder in _cache_dirs():
        for entry in os.scandir(folder):
            if entry.is_file() and entry.name.endswith('.m4b'):
                total += entry.stat().st_size
    return total


def prune_m4b_cache(keep=None):
    """Delete the .m4b files no part uses any more, then the least recently used until the cache is under
    AUDIOBOOK_M4B_CACHE_GB. ``keep`` and files modified in the last 10 minutes are never deleted. A name that does
    not parse (stray *.tmp and *.lock files, older naming schemes) is deleted once it is older than a day.
    Returns the counts and the bytes.
    """
    now = time.time()
    result = {'removed': 0, 'freed_bytes': 0, 'cache_bytes': 0}

    def remove(path, size):
        try:
            os.remove(path)
        except OSError as error:
            logger.warning("Could not prune %s: %s", path, error)
            return False
        result['removed'] += 1
        result['freed_bytes'] += size
        return True

    candidates = []  # (mtime, size, path, protected) of the .m4b files that stay
    for audiobook, folder in _cache_dirs():
        current = _current_names(audiobook)
        for entry in os.scandir(folder):
            if not entry.is_file():
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            age = now - stat.st_mtime
            if CACHE_NAME_RE.fullmatch(entry.name) is None:
                if age > STRAY_TMP_SECONDS:
                    remove(entry.path, stat.st_size)
                continue
            protected = entry.path == keep or age < PROTECTED_SECONDS
            if not protected and entry.name not in current:
                remove(entry.path, stat.st_size)
                continue
            candidates.append((stat.st_mtime, stat.st_size, entry.path, protected))

    total = sum(size for _mtime, size, _path, _protected in candidates)
    cap = int(settings.AUDIOBOOK_M4B_CACHE_GB * 1024 ** 3)
    for _mtime, size, path, protected in sorted(candidates):
        if total <= cap:
            break
        if protected:
            continue
        if remove(path, size):
            total -= size
    result['cache_bytes'] = total
    return result
