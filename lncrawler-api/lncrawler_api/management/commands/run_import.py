import glob
import json
import logging
import os
import shutil
import uuid
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction
from lncrawler_api.models import NovelFromSource
from lncrawler_api.models.source_helpers import truncate
from lncrawler_api.services.folder_guard import locked_move
from lncrawler_api.utils import lncrawler_paths
from lncrawler_api.utils.lncrawler_paths import novel_folder_name

logger = logging.getLogger('lncrawler_api')

# Import novels downloaded outside the app into the library + DB.
#
# A drop folder (settings.IMPORT_FOLDER_PATH, host ./imports) holds novels laid
# out as <novel>/<source>/meta.json. Run:
#   docker compose exec -T api python manage.py run_import               # move (default)
#   docker compose exec -T api python manage.py run_import --action copy
#   docker compose exec -T api python manage.py run_import --dry-run     # report only
# Each source folder is checked first (readable meta.json, chapters on disk, not
# imported yet, its novel has no source of that site, no library folder of that
# name). Then only meta.json, cover.jpg, json/, json.7z and images/ are kept, the
# folder is moved or copied into the library and its rows are written in one
# transaction. A failed import puts the folder back. The sources imported by a
# run are then pruned (prune_library --source-ids).
#
# The background harvest feeder (a thread inside the `scheduler` service,
# toggled in the admin) discovers and imports novels automatically; run_import
# is for bulk-loading a pre-downloaded catalogue.

# Top-level entries of a source folder that survive the import; from_meta_json regenerates the rest.
KEPT_ENTRIES = {'meta.json', 'cover.jpg', 'json', 'json.7z', 'images'}


def _read_meta(meta_path):
    """The parsed meta.json object, or None when the file is not a readable JSON object."""
    try:
        with open(meta_path, encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _has_chapters(source_folder):
    """Whether the folder holds chapters: a json/ dir with a *.json file, or a non-empty json.7z."""
    root = Path(source_folder)
    json_dir = root / 'json'
    if json_dir.is_dir() and any(path.is_file() for path in json_dir.glob('*.json')):
        return True
    archive = root / 'json.7z'
    return archive.is_file() and archive.stat().st_size > 0


def _resolve_novel_dir(library_root, folder_name):
    """``(novel, novel_dir)``: the novel the folder name already maps to (None if none) and the folder it uses."""
    novel = NovelFromSource.resolve_existing_novel(folder_name)
    relative = novel.novel_path if novel is not None and novel.novel_path else folder_name
    return novel, os.path.join(library_root, relative)


def _check_source(source_folder, library_root):
    """Return ``(title, target, skip_reason)``; ``skip_reason`` is None when the folder may be imported."""
    meta = _read_meta(os.path.join(source_folder, 'meta.json'))
    if meta is None:
        return None, None, 'meta.json is not a readable JSON object'
    novel_meta = meta.get('novel') if isinstance(meta.get('novel'), dict) else {}
    title, url = novel_meta.get('title'), novel_meta.get('url')
    if not title or not url:
        return None, None, 'meta.json has no novel title or url'

    source_name = os.path.basename(source_folder)
    novel, novel_dir = _resolve_novel_dir(library_root, novel_folder_name(title))
    target = os.path.join(novel_dir, source_name)
    if not _has_chapters(source_folder):
        return title, target, 'no chapters on disk (json/*.json or json.7z)'
    if NovelFromSource.objects.filter(source_url=truncate(url)).exists():
        return title, target, 'already imported'
    site = lncrawler_paths.site_name_from_folder(source_name)
    if novel is not None and novel.sources.filter(external_source__source_name=site).exists():
        return title, target, f"novel already has a source from {site}"
    if os.path.lexists(target):
        return title, target, 'library folder already exists'
    return title, target, None


def _junk(source_folder):
    """The top-level entries of a source folder that the import does not keep."""
    return sorted(name for name in os.listdir(source_folder) if name not in KEPT_ENTRIES)


def _ignore_junk(source_folder):
    """A copytree ``ignore`` that skips the top-level entries the import does not keep."""
    def ignore(directory, names):
        if directory != source_folder:
            return []
        return [name for name in names if name not in KEPT_ENTRIES]
    return ignore


def _clean(source_folder):
    for name in _junk(source_folder):
        path = os.path.join(source_folder, name)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


def _undo(source_folder, action, folder):
    """Undo the import of ``folder`` (the staging or the renamed folder), logging errors.

    A copy is dropped. A move goes back to ``source_folder``, unless something is there already.
    Returns the path the folder is left at when it could not be put back, else None.
    """
    if not os.path.lexists(folder):
        return None
    try:
        if action == 'copy':
            shutil.rmtree(folder)
        elif os.path.lexists(source_folder):
            logger.error("Import of %s failed and %s exists, so %s is left in place", source_folder, source_folder, folder)
            return folder
        else:
            shutil.move(folder, source_folder)
    except OSError:
        logger.exception("Could not undo the import of %s, folder at %s", source_folder, folder)
        return folder
    return None


def _import_source(source_folder, library_root, title, action):
    """Copy or move a source folder into the library and import it; undo the work on failure.

    The folder is staged at the library root, then renamed into its novel folder under the
    novel's lock. The novel is resolved again under the lock. The rows are written in one
    transaction after the rename. On failure the renamed folder or the staging folder is
    undone, and junk deleted from a moved folder is not restored.
    """
    folder_name = novel_folder_name(title)
    source_name = os.path.basename(source_folder)
    staging = os.path.join(library_root, f".importing-{uuid.uuid4().hex}")
    novel, _ = _resolve_novel_dir(library_root, folder_name)
    renamed, made_dir, novel_dir, target = False, False, None, None
    try:
        if action == 'copy':
            shutil.copytree(source_folder, staging, ignore=_ignore_junk(source_folder))
        else:
            shutil.move(source_folder, staging)
            _clean(staging)
        with locked_move(novel):
            _, novel_dir = _resolve_novel_dir(library_root, folder_name)
            target = os.path.join(novel_dir, source_name)
            if os.path.lexists(target):
                raise FileExistsError(f"library folder appeared meanwhile: {target}")
            made_dir = not os.path.isdir(novel_dir)
            os.makedirs(novel_dir, exist_ok=True)
            os.rename(staging, target)
            renamed = True
        with transaction.atomic():
            novel_from_source = NovelFromSource.from_meta_json(os.path.join(target, 'meta.json'))
    except BaseException as exc:
        left = _undo(source_folder, action, target if renamed else staging)
        if made_dir:
            lncrawler_paths.remove_empty_directory(novel_dir)
        if left:
            exc.add_note(f"folder left at {left}")
        raise
    if action == 'move':
        lncrawler_paths.remove_empty_directory(os.path.dirname(source_folder))
    return novel_from_source


class Command(BaseCommand):
    help = 'Import novels from the import folder specified in settings.IMPORT_FOLDER_PATH'

    def add_arguments(self, parser):
        parser.add_argument(
            '--action',
            choices=['copy', 'move'],
            default='move',
            help='Action to perform with source files: copy (copy to library), or move (move to library)'
        )
        parser.add_argument(
            '--path',
            type=str,
            help='Override the import folder path defined in settings'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would be imported and deleted; change nothing'
        )

    def handle(self, *args, **options):
        import_folder = options.get('path') or settings.IMPORT_FOLDER_PATH
        if not import_folder:
            raise CommandError("IMPORT_FOLDER_PATH is not defined in settings and no path was provided")
        if not os.path.isdir(import_folder):
            raise CommandError(f"Directory not found: {import_folder}")

        action = options['action']
        dry_run = options['dry_run']
        library_root = settings.LNCRAWL_OUTPUT_PATH
        self.stdout.write(self.style.SUCCESS(f"Starting import from: {import_folder}"))
        self.stdout.write(f"Import action: {action}{' (dry run)' if dry_run else ''}")

        meta_files = sorted(glob.glob(os.path.join(glob.escape(import_folder), '*', '*', 'meta.json')))
        if not meta_files:
            self.stdout.write(self.style.WARNING("No meta.json files found 2 folders deep"))
            return
        self.stdout.write(f"Found {len(meta_files)} source folder(s)")

        imported, imported_pks, skipped, failed = 0, [], [], []
        for meta_file in meta_files:
            source_folder = os.path.dirname(meta_file)
            try:
                title, target, reason = _check_source(source_folder, library_root)
                if reason:
                    skipped.append((source_folder, reason))
                    self.stdout.write(f"skip {source_folder}: {reason}")
                elif dry_run:
                    imported += 1
                    self.stdout.write(f"would import {title} -> {target}")
                    label = 'library copy omits' if action == 'copy' else 'would delete'
                    self.stdout.write(f"  {label}: {', '.join(_junk(source_folder)) or 'nothing'}")
                else:
                    novel_from_source = _import_source(source_folder, library_root, title, action)
                    imported += 1
                    imported_pks.append(novel_from_source.pk)
                    self.stdout.write(self.style.SUCCESS(
                        f"Imported '{title}' from {novel_from_source.external_source.source_name}"
                    ))
            except Exception as exc:
                logger.exception("Import failed for %s", source_folder)
                failed.append((source_folder, "; ".join([str(exc), *getattr(exc, '__notes__', [])])))
                self.stdout.write(self.style.ERROR(f"Failed {source_folder}: {exc}"))

        if imported_pks:
            try:
                call_command(
                    'prune_library',
                    apply=True,
                    source_ids=','.join(str(pk) for pk in imported_pks),
                    stdout=self.stdout,
                )
            except Exception as exc:
                logger.exception("prune_library after the import failed")
                self.stdout.write(self.style.ERROR(f"prune_library failed: {exc}"))

        verb = 'would import' if dry_run else 'imported'
        self.stdout.write(self.style.SUCCESS(
            f"Import summary: {imported} {verb}, {len(skipped)} skipped, {len(failed)} failed"
        ))
        for path, reason in skipped:
            self.stdout.write(f"  skipped {path}: {reason}")
        for path, error in failed:
            self.stdout.write(self.style.ERROR(f"  failed {path}: {error}"))
