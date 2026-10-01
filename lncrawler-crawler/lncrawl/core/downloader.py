"""Chapter body/image downloading and the JSON on-disk contract.

Writes:
- <output>/json/<id:05d>.json    one JSON file per chapter
- <output>/images/<md5>.jpg      inline images referenced by chapters
- <output>/cover.jpg             downloaded or generated cover
"""

import json
import logging
from pathlib import Path

from ..models.chapter import Chapter
from ..utils.imgen import generate_cover_image
from .arguments import get_args

logger = logging.getLogger(__name__)


def _chapter_file(chapter: Chapter, output_path: str, pack_by_volume: bool) -> Path:
    dir_name = Path(output_path) / "json"
    if pack_by_volume:
        dir_name = dir_name / ("Volume " + str(chapter.volume).rjust(2, "0"))
    chapter_name = str(chapter.id).rjust(5, "0")
    return dir_name / (chapter_name + ".json")


def _save_chapter(file_name: Path, chapter: Chapter) -> None:
    if not chapter.body:
        chapter.body = "<p><i>Failed to download chapter body</i></p>"

    args = get_args()
    source_notice = (
        f'<br><p><small>Source: <a href="{chapter.url}">{chapter.url}</a></small></p>'
    )
    if args.add_source_url and not chapter.body.endswith(source_notice):
        chapter.body += source_notice

    title = (chapter.title or "").replace("<", "&lt;").replace(">", "&gt;")
    title = f"<h1>{title}</h1>"
    if not chapter.body.startswith(title):
        chapter.body = title + chapter.body

    file_name.parent.mkdir(parents=True, exist_ok=True)
    with file_name.open("w", encoding="utf-8") as fp:
        json.dump(chapter.to_dict(), fp, ensure_ascii=False)


def _same_chapter(old_chapter: dict, chapter: Chapter) -> bool:
    """Guard for incremental re-downloads.

    Chapter ids are positional, so inserting/removing a chapter shifts every
    later id and a cached file would belong to a different chapter. Only trust
    the cache when the stored URL matches the current one.
    """
    old_url = (old_chapter.get("url") or "").rstrip("/")
    # Legacy cached files without a url: fall back to positional trust.
    return not old_url or old_url == (chapter.url or "").rstrip("/")


def fetch_chapter_body(app) -> None:
    from .app import App, Crawler

    assert isinstance(app, App)
    assert isinstance(app.crawler, Crawler)

    file_names = {}
    for chapter in app.chapters:
        file_name = _chapter_file(chapter, app.output_path, app.pack_by_volume)
        file_names[chapter.id] = file_name
        try:
            with open(file_name, "r", encoding="utf-8") as file:
                old_chapter = json.load(file)
            if old_chapter.get("success") and _same_chapter(old_chapter, chapter):
                chapter.update(**old_chapter)
                logger.info(f"Restored chapter {chapter.id} from {file_name}")
                # Already on disk: keep the buffer off-heap for the image phase.
                chapter.body = None
        except FileNotFoundError:
            pass
        except json.JSONDecodeError:
            logger.debug("Unable to decode JSON from the file: %s" % file_name)
        except Exception as e:
            logger.exception("An error occurred while reading the file:", e)

    pending_chapters = [chapter for chapter in app.chapters if not chapter.success]
    app.progress = len(app.chapters) - len(pending_chapters)
    for chapter in app.crawler.download_chapters(pending_chapters):
        app.progress += 1
        _save_chapter(file_names.get(chapter.id), chapter)
        # Written to disk; drop the body so a 3000-chapter novel does not
        # accumulate hundreds of MB in the long-lived worker process.
        chapter.body = None


def _fetch_content_image(app, url: str, image_file: Path) -> None:
    if url and not (image_file.exists() and image_file.is_file()):
        img = None
        try:
            img = app.crawler.download_image(url)
            image_file.parent.mkdir(parents=True, exist_ok=True)
            if img.mode not in ("L", "RGB", "YCbCr", "RGBX"):
                if img.mode == "RGBa":
                    img = img.convert("RGBA").convert("RGB")
                else:
                    img = img.convert("RGB")
            img.save(image_file.as_posix(), "JPEG", optimized=True)
        finally:
            if img is not None:
                try:
                    img.close()
                except Exception:
                    pass
            app.progress += 1


def _fetch_cover_image(app) -> None:
    assert app.crawler is not None

    cover_file = Path(app.output_path) / "cover.jpg"
    if app.crawler.novel_cover:
        try:
            _fetch_content_image(app, app.crawler.novel_cover, cover_file)
        except Exception as e:
            logger.debug("Failed to download cover: %s", e)

    if not cover_file.is_file():
        generate_cover_image(
            cover_file.as_posix(),
            title=app.crawler.novel_title,
            author=app.crawler.novel_author,
        )


def _discard_failed_images(app, chapter, failed) -> None:
    assert app.crawler is not None

    images = chapter.get("images") or {}
    current_failed = [filename for filename in failed if filename in images]
    if not current_failed:
        return

    # The chapter body was dropped from memory after being saved; reload it.
    file_name = _chapter_file(chapter, app.output_path, app.pack_by_volume)
    try:
        with file_name.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except Exception:
        return

    for filename in current_failed:
        images.pop(filename, None)

    body = data.get("body") or ""
    if body:
        soup = app.crawler.make_soup(body)
        for filename in current_failed:
            for img in soup.select(f'img[alt="{filename}"]'):
                img.extract()
        soup_body = soup.select_one("body")
        if soup_body is not None:
            body = "".join(str(x) for x in soup_body.contents)

    data["body"] = body
    data["images"] = dict(images)
    try:
        with file_name.open("w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False)
    except Exception:
        logger.debug("Failed to rewrite chapter %s", chapter.id)


def fetch_chapter_images(app) -> None:
    assert app.crawler is not None

    app.progress = 0
    futures = [app.crawler.executor.submit(_fetch_cover_image, app)]

    image_folder = Path(app.output_path) / "images"
    images_to_download = set(
        (filename, url)
        for chapter in app.chapters
        for filename, url in chapter.get("images", {}).items()
    )
    futures += [
        app.crawler.executor.submit(_fetch_content_image, app, url, image_folder / filename)
        for filename, url in images_to_download
    ]

    failed = []
    try:
        for _ in app.crawler.resolve_as_generator(futures):
            pass
        failed = [
            filename
            for filename, url in images_to_download
            if not (image_folder / filename).is_file()
        ]
    finally:
        logger.info("Processed %d images [%d failed]" % (app.progress, len(failed)))

    for chapter in app.chapters:
        _discard_failed_images(app, chapter, failed)
