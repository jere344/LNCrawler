import os
import logging
import shutil
from pathlib import Path

from django.conf import settings

from ...models import NovelFromSource, PlaceholderCover

logger = logging.getLogger('lncrawler_api')


def is_placeholder_hash(phash) -> bool:
    """Whether ``phash`` was marked as a placeholder cover."""
    if not phash:
        return False
    return PlaceholderCover.objects.filter(cover_phash=phash).exists()


def mark_placeholder(phash) -> PlaceholderCover:
    """Block ``phash`` and remove the cover from every source carrying it."""
    # Imported here: resize imports this module at its top level.
    from .resize import remove_cover

    placeholder, _ = PlaceholderCover.objects.get_or_create(cover_phash=phash)
    sources = NovelFromSource.objects.filter(cover_phash=phash)

    # Keep one thumbnail of the blocked image so the admin can still see it.
    if not placeholder.sample_path:
        for source in sources.iterator():
            if not source.cover_min_path:
                continue
            src_file = Path(settings.LNCRAWL_OUTPUT_PATH) / source.cover_min_path
            if not src_file.is_file():
                continue
            rel = os.path.join('_placeholders', f'{phash}.webp')
            dest = Path(settings.LNCRAWL_OUTPUT_PATH) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src_file, dest)
            placeholder.sample_path = rel
            break

    removed = 0
    for source in sources.iterator():
        try:
            remove_cover(source)
        except Exception:
            # One broken source must not stop the others from losing the placeholder.
            logger.exception("Could not remove placeholder cover from: %s", source.title)
            continue
        removed += 1

    placeholder.removed_count += removed
    placeholder.save(update_fields=['sample_path', 'removed_count'])
    logger.info("Marked cover %s as placeholder: removed %s cover(s)", phash, removed)
    return placeholder
