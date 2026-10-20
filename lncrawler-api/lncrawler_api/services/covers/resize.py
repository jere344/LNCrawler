import os
import logging
from pathlib import Path

from django.conf import settings
from PIL import Image

from .hashing import dhash_file
from .overview import generate_overview
from .placeholders import is_placeholder_hash

logger = logging.getLogger('lncrawler_api')


def generate_cover_min(source, width=200, height=300, quality=80) -> bool:
    """Generate the miniature WebP cover for ``source``."""
    try:
        if not source.cover_path:
            logger.warning("No cover image for: %s", source.title)
            return False

        cover_full_path = Path(settings.LNCRAWL_OUTPUT_PATH) / source.cover_path

        if not cover_full_path.exists():
            logger.warning("Cover image not found at: %s", cover_full_path)
            return False

        output_dir = Path(settings.LNCRAWL_OUTPUT_PATH) / source.source_path
        output_dir.mkdir(parents=True, exist_ok=True)

        cover_min_filename = 'cover.min.webp'
        cover_min_path = output_dir / cover_min_filename

        with Image.open(cover_full_path) as img:
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGB')

            img_width, img_height = img.size
            aspect_ratio = img_width / img_height

            if aspect_ratio > (width / height):
                new_width = width
                new_height = int(width / aspect_ratio)
            else:
                new_height = height
                new_width = int(height * aspect_ratio)

            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            img_resized.save(cover_min_path, 'WEBP', quality=quality)

        # Hash the saved thumbnail (not the full-size source) so import-time and
        # backfill hashes are identical and therefore comparable.
        cover_phash = dhash_file(cover_min_path)

        relative_min_path = os.path.join(source.source_path, cover_min_filename)
        if is_placeholder_hash(cover_phash):
            logger.info("Dropping placeholder cover for: %s (hash %s)", source.title, cover_phash)
            # Point the source at the file just written so remove_cover deletes it too.
            source.cover_min_path = relative_min_path
            remove_cover(source)
            return False

        source.cover_min_path = relative_min_path
        source.cover_phash = cover_phash
        source.save(update_fields=['cover_min_path', 'cover_phash'])

        logger.info("Generated miniature cover for: %s", source.title)
        return True
    except Exception as e:
        logger.error("Failed to generate miniature cover for %s: %s", source.title, e)
        return False


def remove_cover(source) -> None:
    """Delete ``source``'s cover files and clear every cover field, then redraw the OG image."""
    # The old overview still shows the cover, so it goes too, and its path is cleared
    # before the re-render: a failed re-render then never leaves the placeholder visible.
    for rel in (source.cover_path, source.cover_min_path, source.overview_picture_path):
        if not rel:
            continue
        try:
            (Path(settings.LNCRAWL_OUTPUT_PATH) / rel).unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning("Could not delete %s: %s", rel, e)
    # cover_url is cleared too: seo_views would fall back to the remote image.
    source.cover_path = None
    source.cover_min_path = None
    source.cover_phash = None
    source.cover_url = None
    source.overview_picture_path = None
    source.save(update_fields=[
        'cover_path', 'cover_min_path', 'cover_phash', 'cover_url', 'overview_picture_path',
    ])
    generate_overview(source)
