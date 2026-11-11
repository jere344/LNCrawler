"""Which source names a novel: ``Novel.canonical_source``, kept by ``refresh_naming``.

``sync_novel_naming`` applies it to the slug and the folder: it recomputes every novel's canonical
source, then renames the folders that no longer match (the scheduled task and the management command).
"""

import json
import logging
import os
from collections import Counter, defaultdict, namedtuple

from django.conf import settings
from django.db import IntegrityError

from ..models import Novel, NovelAlias, NovelFromSource
from ..utils.crawler_path import META_FILE_NAME
from ..utils.lncrawler_paths import novel_folder_name
from ..utils.query_helpers import language_tier, rank_sources
from ..utils.slug import slugify
from .folder_guard import FolderBusy, locked_move

logger = logging.getLogger('lncrawler_api')

# A challenger replaces the current canonical source only with this many more net votes.
NAMING_VOTE_MARGIN = 2

# Folder renames attempted per run of ``sync_novel_naming``. A busy novel does not count.
DEFAULT_RENAME_LIMIT = 5

# How many suffixed folder names ("foo 2", "foo 3", ...) a reconcile looks at for a crashed rename.
ADOPT_SUFFIX_LIMIT = 10


def _net_votes(source):
    return source.upvotes - source.downvotes


def choose_canonical(sources, current):
    """The source that should name the novel, given its ``current`` canonical source.

    Without a current one, or when it is not among ``sources``, the best ranked source wins.
    Otherwise the current one stays unless the best is in a better language tier or has
    ``NAMING_VOTE_MARGIN`` more net votes, so close votes do not rename the folder back and forth.
    """
    languages = [settings.NAMING_LANGUAGE]
    best = rank_sources(sources, languages)
    if best is None or current is None or not any(s.pk == current.pk for s in sources):
        return best
    if best.pk == current.pk:
        return current
    if language_tier(best, languages) < language_tier(current, languages):
        return best
    if _net_votes(best) - _net_votes(current) >= NAMING_VOTE_MARGIN:
        return best
    return current


def refresh_naming(novel):
    """Store the canonical source of ``novel`` again, when it changed. Keeps the caller's transaction.

    A novel without sources is left alone.
    """
    # A fresh query, not ``novel.sources.all()``: the instance may carry a prefetched list that
    # still holds sources a merge or split has just deleted or moved.
    sources = list(NovelFromSource.objects.filter(novel_id=novel.pk))
    if not sources:
        return
    stored_id = Novel.objects.filter(pk=novel.pk).values_list('canonical_source_id', flat=True).first()
    current = next((s for s in sources if s.pk == stored_id), None)
    chosen = choose_canonical(sources, current)
    if chosen.pk != stored_id:
        Novel.objects.filter(pk=novel.pk).update(canonical_source=chosen)
    novel.canonical_source_id = chosen.pk


def refresh_naming_by_id(novel_id):
    """``refresh_naming`` for a novel found by id; a no-op when the novel no longer exists."""
    novel = Novel.objects.filter(pk=novel_id).first()
    if novel is not None:
        refresh_naming(novel)


# ---------------------------------------------------------------------------
# Sync task
# ---------------------------------------------------------------------------

_Candidate = namedtuple('_Candidate', 'pk language upvotes downvotes available_chapters_count title')
_Planned = namedtuple('_Planned', 'novel chosen desired')


class _Skip(Exception):
    """A planned change cannot be made now; the reason is logged and the next run retries."""


def _say(stdout, text):
    """Log ``text``, and write it to ``stdout`` when a command runs the sync."""
    logger.info(text)
    if stdout is not None:
        stdout.write(text + "\n")


class _Names:
    """The folder and slug names in use, for picking a free one.

    ``disk`` maps the lower-cased name of each entry of the library root to its exact name: NTFS is
    case-insensitive, so the lower-case key is the check. ``folders``, ``slugs`` and ``aliases`` map
    the lower-cased ``novel_path``, the slug and each alias slug to the pk of the novel holding it.
    ``claim`` applies a change made during the run, so the next pick sees it.
    """

    def __init__(self, root_names, novel_rows, alias_rows):
        self.disk = {name.lower(): name for name in root_names}
        self.folders = {}
        self.slugs = {}
        for pk, path, slug in novel_rows:
            self.folders.setdefault(path.lower(), pk)
            self.slugs[slug] = pk
        self.aliases = dict(alias_rows)

    @classmethod
    def load(cls):
        root = settings.LNCRAWL_OUTPUT_PATH
        names = os.listdir(root) if os.path.isdir(root) else []
        novel_rows = Novel.objects.values_list('pk', 'novel_path', 'slug')
        alias_rows = NovelAlias.objects.values_list('slug', 'novel_id')
        return cls(names, novel_rows, alias_rows)

    def exists(self, folder):
        """Whether ``folder`` is on disk, whatever its case."""
        return folder.lower() in self.disk

    def claimed_by_other(self, folder, pk):
        """Whether another novel holds the path or the slug of ``folder``, or an alias of that slug."""
        if self.folders.get(folder.lower(), pk) != pk:
            return True
        slug = slugify(folder, max_length=255)
        return self.slugs.get(slug, pk) != pk or self.aliases.get(slug, pk) != pk

    def is_free(self, folder, pk, own_folder=None):
        taken_on_disk = self.exists(folder) and folder.lower() != (own_folder or '').lower()
        return not taken_on_disk and not self.claimed_by_other(folder, pk)

    def pick(self, desired, pk, own_folder=None):
        """``desired`` when free, else the first free one of ``desired 2``, ``desired 3``, ..."""
        folder, number = desired, 1
        while not self.is_free(folder, pk, own_folder):
            number += 1
            folder = f"{desired} {number}"
        return folder

    def claim(self, pk, old_folder, old_slug, new_folder, new_slug):
        """Record that novel ``pk`` moved from ``old_folder`` to ``new_folder`` and from ``old_slug`` to ``new_slug``."""
        self.disk.pop(old_folder.lower(), None)
        self.disk[new_folder.lower()] = new_folder
        if self.folders.get(old_folder.lower()) == pk:
            del self.folders[old_folder.lower()]
        self.folders[new_folder.lower()] = pk
        if self.slugs.get(old_slug) == pk:
            del self.slugs[old_slug]
        self.slugs[new_slug] = pk
        if old_slug != new_slug:
            self.aliases.setdefault(old_slug, pk)
        if self.aliases.get(new_slug) == pk:
            del self.aliases[new_slug]


def _sources_by_novel():
    """The ranking fields of every source, grouped by novel: one query for the whole library."""
    grouped = defaultdict(list)
    rows = NovelFromSource.objects.filter(novel_id__isnull=False).values_list(
        'pk', 'novel_id', 'title', 'language', 'upvotes', 'downvotes', 'available_chapters_count',
    )
    for pk, novel_id, title, language, upvotes, downvotes, chapters in rows.iterator(chunk_size=2000):
        grouped[novel_id].append(_Candidate(pk, language, upvotes, downvotes, chapters, title))
    return grouped


def _fresh_choice(novel_pk):
    """The canonical source of novel ``novel_pk`` and its folder, from the rows as they are now."""
    sources = list(NovelFromSource.objects.filter(novel_id=novel_pk))
    if not sources:
        return None, None
    stored_id = Novel.objects.filter(pk=novel_pk).values_list('canonical_source_id', flat=True).first()
    current = next((s for s in sources if s.pk == stored_id), None)
    chosen = choose_canonical(sources, current)
    return chosen, novel_folder_name(chosen.title)


def _source_rows(novel_pk):
    """(source folder, source URL) of each source of a novel that has a source folder."""
    rows = (
        NovelFromSource.objects.filter(novel_id=novel_pk)
        .exclude(source_folder__isnull=True)
        .exclude(source_folder='')
    )
    return list(rows.values_list('source_folder', 'source_url'))


def _meta_url(path):
    """The source URL a meta.json names, or None when it cannot be read."""
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    novel = data.get('novel') if isinstance(data, dict) else None
    url = novel.get('url') if isinstance(novel, dict) else None
    return url or None


def _holds_novel_sources(root, folder, rows):
    """Whether ``folder`` holds a source of the novel: a source folder whose meta.json names that source's URL."""
    return any(
        source_url and _meta_url(os.path.join(root, folder, source_folder, META_FILE_NAME)) == source_url
        for source_folder, source_url in rows
    )


def _adoptable_folder(names, novel, desired, rows):
    """The folder a crashed rename of ``novel`` left behind: ``desired`` or a suffixed name, as it is on disk.

    It must belong to no other novel and hold a source of this one (see ``_holds_novel_sources``).
    """
    root = settings.LNCRAWL_OUTPUT_PATH
    for number in range(1, ADOPT_SUFFIX_LIMIT + 1):
        wanted = desired if number == 1 else f"{desired} {number}"
        exact = names.disk.get(wanted.lower())
        if exact is None or names.claimed_by_other(exact, novel.pk):
            continue
        if _holds_novel_sources(root, exact, rows):
            return exact
    return None


def _check_alias_free(novel, slug):
    """Refuse a move whose old slug is another novel's alias: the old URL must keep naming ``novel``."""
    if slug != novel.slug and NovelAlias.objects.filter(slug=novel.slug).exclude(novel_id=novel.pk).exists():
        raise _Skip(f"alias '{novel.slug}' belongs to another novel")


def _write_move(novel, folder, slug, canonical_pk):
    """Store a folder move in the rows: folder name, slug and canonical source, with the old slug as an alias.

    An alias of the new slug that this novel owns is removed (renaming back to an earlier name).
    Another novel's alias is never touched.
    """
    old_slug = novel.slug
    Novel.objects.filter(pk=novel.pk).update(novel_path=folder, slug=slug, canonical_source_id=canonical_pk)
    if old_slug != slug:
        NovelAlias.objects.get_or_create(slug=old_slug, defaults={'novel_id': novel.pk})
    NovelAlias.objects.filter(slug=slug, novel_id=novel.pk).delete()


def _record_move(folder, slug, canonical_pk):
    """A change that only rewrites the rows (a folder adopted after a crash)."""
    def change(current, files):
        _check_alias_free(current, slug)
        _write_move(current, folder, slug, canonical_pk)
    return change


def _rename_move(folder, slug, canonical_pk):
    """A change that renames the folder on disk, then rewrites the rows. Runs under the folder lock."""
    def change(current, files):
        root = settings.LNCRAWL_OUTPUT_PATH
        old_abs = os.path.join(root, current.novel_path)
        new_abs = os.path.join(root, folder)
        if not os.path.isdir(old_abs):
            raise _Skip(f"folder '{current.novel_path}' is missing on disk")
        same_folder = folder.lower() == current.novel_path.lower()
        if os.path.lexists(new_abs) and not (same_folder and os.path.samefile(old_abs, new_abs)):
            raise _Skip(f"'{folder}' exists on disk")
        _check_alias_free(current, slug)
        files.move(old_abs, new_abs)
        _write_move(current, folder, slug, canonical_pk)
    return change


def _locked_change(novel, expected, change):
    """Run ``change(current, files)`` for ``novel`` under its folder lock, with a FileJournal.

    ``expected`` is the (canonical pk, folder) the plan was made for. Under the lock the row and the
    canonical source are read again: a change that no longer applies is skipped, not made.
    Returns None when the change was made, else the reason it was not: ``"busy"`` for a folder guard
    refusal (not counted toward the rename limit), or the message of the skip or failure. Nothing is
    changed on a failure: the journal reverses the disk and the transaction the rows.
    """
    from .novel_operations import FileOperationError, file_journal

    try:
        with file_journal() as files, locked_move(novel):
            current = Novel.objects.get(pk=novel.pk)
            if current.novel_path != novel.novel_path:
                raise _Skip("the folder changed during this run")
            chosen, desired = _fresh_choice(novel.pk)
            if chosen is None:
                raise _Skip("the novel has no sources left")
            if desired == current.novel_path:
                raise _Skip("its folder already matches its canonical source")
            if (chosen.pk, desired) != expected:
                raise _Skip("its canonical source changed during this run")
            change(current, files)
    except FolderBusy:
        return "busy"
    except _Skip as exc:
        return str(exc)
    except (OSError, FileOperationError, IntegrityError) as exc:
        logger.warning("Novel %s: rename failed, retried next run: %s", novel.slug, exc)
        return f"failed, retried next run: {exc}"
    return None


def sync_novel_naming(limit=DEFAULT_RENAME_LIMIT, dry_run=False, stdout=None):
    """Make each novel's canonical source, slug and folder agree. Returns the counts of what was done.

    1. Canonical: novels whose folder stays get their new canonical source, each with a compare-and-set
       (a change made meanwhile is kept and the next run decides).
    2. Folders, only when some novel's folder differs from its desired one (otherwise the folders are not
       listed): a folder a crashed rename left under its new name is adopted (rows only), then at most
       ``limit`` folders are renamed (a busy novel does not count), each with its slug, alias and canonical
       source, through the folder guard.

    ``dry_run`` changes nothing and lists what a run would do; it does not apply ``limit``.
    ``stdout`` receives the same lines as the log when a command runs the sync.
    """
    counts = Counter()
    sources = _sources_by_novel()
    plan = []
    for novel in Novel.objects.only('pk', 'slug', 'novel_path', 'canonical_source'):
        candidates = sources.get(novel.pk)
        if not candidates:
            continue
        current = next((c for c in candidates if c.pk == novel.canonical_source_id), None)
        chosen = choose_canonical(candidates, current)
        plan.append(_Planned(novel, chosen, novel_folder_name(chosen.title)))

    def say(text):
        _say(stdout, text)

    moves = [item for item in plan if item.novel.novel_path != item.desired]
    canonical = [
        item for item in plan
        if item.novel.novel_path == item.desired and item.novel.canonical_source_id != item.chosen.pk
    ]

    for item in canonical:
        say(f"canonical {item.novel.slug}: {item.chosen.title}")
    if canonical:
        counts['canonical'] = len(canonical)
        if not dry_run:
            counts['canonical'] = sum(
                Novel.objects.filter(pk=item.novel.pk, canonical_source_id=item.novel.canonical_source_id)
                .update(canonical_source_id=item.chosen.pk)
                for item in canonical
            )

    if moves:
        names = _Names.load()

        def perform(item, folder, slug, kind):
            """Do one folder move, or only plan it in a dry run. Returns "busy", "skipped" or None."""
            novel = item.novel
            if kind == 'rename':
                detail = f"folder '{novel.novel_path}' -> '{folder}', slug {novel.slug} -> {slug}"
                past = 'renamed'
            else:
                detail = (f"folder '{novel.novel_path}' is missing, '{folder}' holds its sources, "
                          f"slug {novel.slug} -> {slug}")
                past = 'adopted'
            if dry_run:
                counts[past] += 1
                say(f"would {kind} {novel.slug}: {detail}")
                names.claim(novel.pk, novel.novel_path, novel.slug, folder, slug)
                return None
            change = _record_move(folder, slug, item.chosen.pk) if kind == 'adopt' else _rename_move(
                folder, slug, item.chosen.pk)
            reason = _locked_change(novel, (item.chosen.pk, item.desired), change)
            if reason == 'busy':
                counts['busy'] += 1
                say(f"busy {novel.slug}: {kind} skipped, retried next run")
                return 'busy'
            if reason:
                counts['skipped'] += 1
                say(f"skipped {novel.slug}: {reason}")
                return 'skipped'
            counts[past] += 1
            say(f"{past} {novel.slug}: {detail}")
            names.claim(novel.pk, novel.novel_path, novel.slug, folder, slug)
            return None

        # Reconcile: a folder that is missing under the row's name may be one a crashed rename left.
        missing = [item for item in moves if not names.exists(item.novel.novel_path)]
        found = set()
        for item in missing:
            folder = _adoptable_folder(names, item.novel, item.desired, _source_rows(item.novel.pk))
            if folder is None:
                continue
            found.add(item.novel.pk)
            perform(item, folder, slugify(folder, max_length=255), 'adopt')
        if missing and len(found) < len(missing):
            counts['missing'] = len(missing) - len(found)

        queue = sorted(
            (item for item in moves if item.novel.pk not in found and names.exists(item.novel.novel_path)),
            key=lambda item: item.novel.slug,
        )
        attempted = 0
        for item in queue:
            if not dry_run and attempted >= limit:
                break
            folder = names.pick(item.desired, item.novel.pk, own_folder=item.novel.novel_path)
            if folder != item.desired:
                counts['collision'] += 1
                say(f"collision {item.novel.slug}: '{item.desired}' is taken, using '{folder}'")
            if perform(item, folder, slugify(folder, max_length=255), 'rename') != 'busy':
                attempted += 1

    result = dict(counts)
    say(f"sync_novel_naming{' (dry run)' if dry_run else ''}: {result or 'nothing to do'}")
    return result


def free_novel_folder(desired):
    """A folder name for a new novel named after ``desired``: the name when free, else a suffixed one.

    Free means: not on disk (case-insensitive), not another novel's folder, and its slug is neither
    another novel's slug nor another novel's alias. Same rule as the sync task.
    """
    return _Names.load().pick(desired, None)


def create_free_novel_folder(desired, attempts=5):
    """Pick a free novel folder for ``desired`` and create it at once, so the name is taken.

    A folder another process creates between the pick and the ``mkdir`` is skipped: the pick is
    made again. Raises ``FileExistsError`` after ``attempts`` tries.
    """
    root = settings.LNCRAWL_OUTPUT_PATH
    for _ in range(attempts):
        folder = free_novel_folder(desired)
        try:
            os.mkdir(os.path.join(root, folder))
        except FileExistsError:
            continue
        return folder
    raise FileExistsError(f"no free novel folder for '{desired}' after {attempts} tries")
