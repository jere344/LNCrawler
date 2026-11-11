"""Split the stored paths into names relative to their parent. No folder on disk is touched.

- Novel.novel_path: an empty value is filled from the parent folder of the first source that has a
  path, else from the slug. An existing value is normalised (absolute under LNCRAWL_OUTPUT_PATH
  stripped, backslashes read as separators). It must end up a single folder name, otherwise the
  migration raises PathSplitError and nothing is written.
- Folder names are compared case-insensitively. Adoption: when no source of a novel is in its novel
  folder and all of them share one top-level folder, that folder (exact case as stored) becomes
  novel_path. DB only.
- NovelFromSource.source_folder is the source path's last part when the source is directly inside its
  novel folder. A source whose stored path is not that (a folder split from its novel folder, a
  nested folder name, an unusable path) is deleted, with its chapters and other user data. Its files
  stay on disk; the orphan-folder prune handles them. One WARNING line per deleted row is logged.
- A novel left without any source is deleted, as in 0117. A novel whose canonical_source was deleted
  gets the best remaining source, with the 0117 ranking.
- A source with no stored path keeps its row; covers that cannot be placed are cleared.
- cover_file, cover_min_file and overview_picture_file must be inside the source folder; one that is
  not is set to NULL (logged and counted). Audiobook.cover_file, AudiobookChapter.file_in_source and
  each AudiobookPart.uploads entry's 'file_in_source' are relative to the source folder; a file that
  cannot be written that way is dropped (not written, logged and counted).

Reversing rebuilds the old full paths from the new fields. Deleted rows are not restored.
"""

import logging
import os
import re
from collections import Counter, defaultdict

from django.conf import settings
from django.db import migrations

logger = logging.getLogger('lncrawler_api')

BATCH_SIZE = 1000
SHOWN_PROBLEMS = 50
SHOWN_PKS = 50


class PathSplitError(Exception):
    """A novel_path that is not a single folder name; nothing was written."""


def _key(name):
    """Comparison key for a folder name: NTFS ignores case."""
    return name.casefold()


def _relative(path, root):
    """``path`` as a '/'-separated path relative to ``root``. '' when empty, None when unusable."""
    if not path:
        return ''
    value = path.replace('\\', '/')
    if value.startswith('/') or re.match(r'^[A-Za-z]:/', value):
        base = root.replace('\\', '/').rstrip('/')
        if not base or not value.startswith(base + '/'):
            return None
        value = value[len(base) + 1:]
    parts = [part for part in value.split('/') if part not in ('', '.')]
    if '..' in parts:
        return None
    return '/'.join(parts)


def _inside(path, folder):
    """``path`` relative to ``folder`` (both relative, names compared case-insensitively), or None."""
    if not path or not folder:
        return None
    parts = path.split('/')
    names = folder.split('/')
    count = len(names)
    if len(parts) <= count or [_key(part) for part in parts[:count]] != [_key(name) for name in names]:
        return None
    return '/'.join(parts[count:])


def _file_in_source(value, root, source_rel, label, pk, novel_path, done):
    """``value`` relative to the source folder ``source_rel``. None (logged, counted) when it is not inside it."""
    if not value:
        return None
    inside = _inside(_relative(value, root), source_rel) if source_rel else None
    if inside is None:
        logger.warning("Migration 0120 dropped %s pk=%s path=%r novel_path=%r: not inside its source folder",
                       label, pk, value, novel_path)
        done['files dropped'] += 1
    return inside


def _rank(row):
    """Ranking key of a (source_id, novel_id, language, upvotes, downvotes, chapters, title) row.

    Copied from 0117 (set_canonical_sources): English first, then net votes, upvotes, chapters, title.
    """
    _, _, language, upvotes, downvotes, chapters, title = row
    tier = 0 if language == 'en' else 1
    return (tier, -(upvotes - downvotes), -upvotes, -chapters, title)


def _update(model, objects, fields):
    """bulk_update the objects of an iterable, BATCH_SIZE at a time."""
    batch = []
    for obj in objects:
        batch.append(obj)
        if len(batch) >= BATCH_SIZE:
            model.objects.bulk_update(batch, fields, batch_size=BATCH_SIZE)
            batch = []
    if batch:
        model.objects.bulk_update(batch, fields, batch_size=BATCH_SIZE)


def _delete(model, pks):
    """Delete the rows with these pks (cascading), BATCH_SIZE at a time."""
    pks = sorted(pks)
    for start in range(0, len(pks), BATCH_SIZE):
        model.objects.filter(pk__in=pks[start:start + BATCH_SIZE]).delete()


class _Plan:
    """Everything the migration writes, computed before anything is written."""

    def __init__(self):
        self.novels = {}           # novel pk -> new novel_path (only the changed ones)
        self.delete_novels = set()
        self.delete_sources = set()
        self.canonical = {}        # novel pk -> new canonical_source pk
        self.sources = {}          # source pk -> {field: value}
        self.audiobooks = {}       # audiobook pk -> cover_file
        self.chapters = {}         # chapter pk -> file_in_source
        self.parts = {}            # part pk -> uploads


def _novel_folder(novel_id, slug, raw, rels, root, done, problems):
    """The novel folder as a single relative name, or None when it is not one (a problem is recorded)."""
    if raw:
        folder = _relative(raw, root)
    else:
        parent = next((rel.rpartition('/')[0] for rel in rels if rel and '/' in rel), '')
        folder = parent or slug
        done['novel_path filled ' + ('from its first source' if parent else 'from the slug')] += 1
    if not folder or '/' in folder:
        problems.append(('novel', novel_id, raw or folder, raw or folder,
                         'novel_path is not a single relative folder name'))
        return None
    if raw and folder != raw:
        done['novel_path normalised'] += 1
    return folder


def _plan(models, root, done, problems):
    Novel = models['Novel']
    NovelFromSource = models['NovelFromSource']
    plan = _Plan()

    canonical_of = dict(Novel.objects.values_list('pk', 'canonical_source_id'))
    rows = defaultdict(list)
    for pk, novel_id, source_path, cover, cover_min, overview, language, upvotes, downvotes, chapters, title in (
        NovelFromSource.objects.order_by('pk')
        .values_list('pk', 'novel_id', 'source_path', 'cover_path', 'cover_min_path', 'overview_picture_path',
                     'language', 'upvotes', 'downvotes', 'available_chapters_count', 'title')
        .iterator(chunk_size=5000)
    ):
        rank_row = (pk, novel_id, language, upvotes, downvotes, chapters, title)
        rows[novel_id].append((pk, source_path, _relative(source_path, root), cover, cover_min, overview, rank_row))

    # Per source pk: (source folder the source's files are relative to, or None, stored novel_path).
    audio_base = {}

    for novel_id, slug, raw in Novel.objects.order_by('pk').values_list('pk', 'slug', 'novel_path'):
        entries = rows.get(novel_id, [])
        folder = _novel_folder(novel_id, slug, raw, [entry[2] for entry in entries], root, done, problems)
        if folder is None:
            continue

        usable = [entry for entry in entries if entry[2] and '/' in entry[2]]
        tops = [entry[2].split('/', 1)[0] for entry in usable]
        if tops and len({_key(top) for top in tops}) == 1 and not any(_key(top) == _key(folder) for top in tops):
            folder = tops[0]
            done['novel_path adopted from its sources'] += 1
            logger.info("Migration 0120 novel pk=%s: no source in %r, adopted folder %r", novel_id, raw, folder)
        if folder != raw:
            plan.novels[novel_id] = folder

        doomed = set()
        for pk, source_path, rel, cover, cover_min, overview, _rank_row in entries:
            source_rel = None
            name = None
            if rel and '/' in rel:
                top, after = rel.split('/', 1)
                if _key(top) == _key(folder) and '/' not in after:
                    source_rel = rel
                    name = after

            if source_rel is None and source_path:
                # A stored path that is not one folder directly inside the novel folder: delete the row.
                logger.warning("Migration 0120 deleted source pk=%s path=%r novel_path=%r: "
                               "not a single folder directly inside its novel folder", pk, source_path, raw)
                done['sources deleted'] += 1
                plan.delete_sources.add(pk)
                doomed.add(pk)
                continue

            audio_base[pk] = (source_rel, raw)
            if source_rel is None:
                # No stored path: nothing to split. Clear covers that cannot be placed.
                if cover or cover_min or overview:
                    logger.warning("Migration 0120 cleared the covers of source pk=%s: it has no path (novel_path=%r)",
                                   pk, raw)
                    done['files dropped'] += 1
                    plan.sources[pk] = {'source_folder': None, 'cover_file': None,
                                        'cover_min_file': None, 'overview_picture_file': None}
                continue

            plan.sources[pk] = {
                'source_folder': name,
                'cover_file': _file_in_source(cover, root, source_rel, 'source cover', pk, raw, done),
                'cover_min_file': _file_in_source(cover_min, root, source_rel, 'source cover_min', pk, raw, done),
                'overview_picture_file': _file_in_source(overview, root, source_rel, 'source overview', pk, raw, done),
            }
            done['sources split'] += 1

        if entries and len(doomed) == len(entries):
            plan.delete_novels.add(novel_id)
            plan.novels.pop(novel_id, None)
            done['novels deleted'] += 1
            continue
        if canonical_of.get(novel_id) in doomed:
            remaining = [entry[6] for entry in entries if entry[0] not in doomed]
            plan.canonical[novel_id] = min(remaining, key=_rank)[0]
            done['canonical source re-picked'] += 1

    for pk in plan.delete_sources:
        plan.sources.pop(pk, None)
    if plan.delete_novels:
        logger.warning("Migration 0120 deleted %s novel(s) whose sources were all deleted, first pks: %s",
                       len(plan.delete_novels), sorted(plan.delete_novels)[:SHOWN_PKS])

    _split_audio(models, root, audio_base, plan, done)
    return plan


def _split_audio(models, root, audio_base, plan, done):
    Audiobook = models['Audiobook']
    AudiobookChapter = models['AudiobookChapter']
    AudiobookPart = models['AudiobookPart']

    for pk, cover, source_id in Audiobook.objects.values_list('pk', 'cover_path', 'source_id').iterator(chunk_size=2000):
        if not cover or source_id in plan.delete_sources:
            continue
        source_rel, novel_path = audio_base.get(source_id, (None, None))
        inside = _file_in_source(cover, root, source_rel, 'audiobook cover', pk, novel_path, done)
        if inside is not None:
            plan.audiobooks[pk] = inside
            done['audiobook covers split'] += 1

    rows = AudiobookChapter.objects.values_list('pk', 'file_path', 'part__audiobook__source_id').iterator(chunk_size=5000)
    for pk, file_path, source_id in rows:
        if not file_path or source_id in plan.delete_sources:
            continue
        source_rel, novel_path = audio_base.get(source_id, (None, None))
        inside = _file_in_source(file_path, root, source_rel, 'audio chapter', pk, novel_path, done)
        if inside is not None:
            plan.chapters[pk] = inside
            done['audio chapters split'] += 1

    rows = AudiobookPart.objects.order_by('pk').values_list('pk', 'uploads', 'audiobook__source_id').iterator(chunk_size=2000)
    for pk, uploads, source_id in rows:
        if not uploads or source_id in plan.delete_sources:
            continue
        source_rel, novel_path = audio_base.get(source_id, (None, None))
        new_uploads = {}
        for key, upload in uploads.items():
            if not isinstance(upload, dict):
                logger.warning("Migration 0120 dropped audiobook part pk=%s upload %s: not an object", pk, key)
                done['files dropped'] += 1
                continue
            inside = _file_in_source(upload.get('file_path'), root, source_rel, 'audiobook part upload',
                                     pk, novel_path, done)
            if inside is None:
                continue
            entry = {name: value for name, value in upload.items() if name != 'file_path'}
            entry['file_in_source'] = inside
            new_uploads[key] = entry
            done['uploads split'] += 1
        plan.parts[pk] = new_uploads


def _write(models, plan):
    Novel = models['Novel']
    NovelFromSource = models['NovelFromSource']
    _update(Novel, (Novel(pk=pk, novel_path=value) for pk, value in plan.novels.items()), ['novel_path'])
    _delete(Novel, plan.delete_novels)
    _delete(NovelFromSource, plan.delete_sources)
    _update(NovelFromSource, (NovelFromSource(pk=pk, **fields) for pk, fields in plan.sources.items()),
            ['source_folder', 'cover_file', 'cover_min_file', 'overview_picture_file'])
    Audiobook = models['Audiobook']
    _update(Audiobook, (Audiobook(pk=pk, cover_file=value) for pk, value in plan.audiobooks.items()), ['cover_file'])
    Chapter = models['AudiobookChapter']
    _update(Chapter, (Chapter(pk=pk, file_in_source=value) for pk, value in plan.chapters.items()), ['file_in_source'])
    Part = models['AudiobookPart']
    _update(Part, (Part(pk=pk, uploads=value) for pk, value in plan.parts.items()), ['uploads'])
    _update(Novel, (Novel(pk=pk, canonical_source_id=value) for pk, value in plan.canonical.items()),
            ['canonical_source'])


def split_paths(apps, schema_editor):
    root = settings.LNCRAWL_OUTPUT_PATH
    models = {
        name: apps.get_model('lncrawler_api', name)
        for name in ('Novel', 'NovelFromSource', 'Audiobook', 'AudiobookChapter', 'AudiobookPart')
    }

    done = Counter()
    problems = []
    plan = _plan(models, root, done, problems)

    if problems:
        lines = [
            f"{label} pk={pk} path={path!r} novel_path={novel_path!r}: {reason}"
            for label, pk, path, novel_path, reason in problems[:SHOWN_PROBLEMS]
        ]
        if len(problems) > SHOWN_PROBLEMS:
            lines.append(f"... and {len(problems) - SHOWN_PROBLEMS} more")
        raise PathSplitError(
            f"Migration 0120 stopped: {len(problems)} novel_path value(s) are not a single folder name. "
            "Nothing was changed. Fix these rows, then migrate again:\n" + "\n".join(lines)
        )

    _write(models, plan)
    logger.info("Migration 0120 path split: %s", dict(done))


def _join(*parts):
    return os.path.join(*parts) if all(parts) else None


def join_paths(apps, schema_editor):
    """Rebuild the full stored paths from the new fields, for a reverse migration. Deleted rows are not restored."""
    NovelFromSource = apps.get_model('lncrawler_api', 'NovelFromSource')
    Audiobook = apps.get_model('lncrawler_api', 'Audiobook')
    AudiobookChapter = apps.get_model('lncrawler_api', 'AudiobookChapter')
    AudiobookPart = apps.get_model('lncrawler_api', 'AudiobookPart')

    def sources():
        rows = NovelFromSource.objects.values_list(
            'pk', 'novel__novel_path', 'source_folder', 'cover_file', 'cover_min_file', 'overview_picture_file',
        ).iterator(chunk_size=5000)
        for pk, novel_path, folder, cover, cover_min, overview in rows:
            source_path = _join(novel_path, folder)
            yield NovelFromSource(
                pk=pk,
                source_path=source_path,
                cover_path=_join(source_path, cover),
                cover_min_path=_join(source_path, cover_min),
                overview_picture_path=_join(source_path, overview),
            )

    def audiobooks():
        rows = Audiobook.objects.values_list('pk', 'cover_file', 'source__source_folder', 'source__novel__novel_path').iterator(chunk_size=2000)
        for pk, cover, folder, novel_path in rows:
            yield Audiobook(pk=pk, cover_path=_join(_join(novel_path, folder), cover) or '')

    def chapters():
        rows = (
            AudiobookChapter.objects.values_list(
                'pk', 'file_in_source', 'part__audiobook__source__source_folder', 'part__audiobook__source__novel__novel_path',
            ).iterator(chunk_size=5000)
        )
        for pk, file_in_source, folder, novel_path in rows:
            yield AudiobookChapter(pk=pk, file_path=_join(_join(novel_path, folder), file_in_source) or '')

    def parts():
        rows = AudiobookPart.objects.order_by('pk').values_list(
            'pk', 'uploads', 'audiobook__source__source_folder', 'audiobook__source__novel__novel_path',
        ).iterator(chunk_size=2000)
        for pk, uploads, folder, novel_path in rows:
            if not uploads:
                continue
            source_rel = _join(novel_path, folder)
            new_uploads = {}
            for key, upload in uploads.items():
                entry = {name: value for name, value in upload.items() if name != 'file_in_source'}
                entry['file_path'] = _join(source_rel, upload.get('file_in_source')) or ''
                new_uploads[key] = entry
            yield AudiobookPart(pk=pk, uploads=new_uploads)

    _update(NovelFromSource, sources(), ['source_path', 'cover_path', 'cover_min_path', 'overview_picture_path'])
    _update(Audiobook, audiobooks(), ['cover_path'])
    _update(AudiobookChapter, chapters(), ['file_path'])
    _update(AudiobookPart, parts(), ['uploads'])


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0119_path_storage_fields'),
    ]

    operations = [
        migrations.RunPython(split_paths, join_paths),
    ]
