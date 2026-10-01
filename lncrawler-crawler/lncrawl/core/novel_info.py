import json
import re
from pathlib import Path
from typing import Dict

from ..constants import META_FILE_NAME
from ..models import Chapter, MetaInfo, Novel, NovelStatus, Session, Volume
from .crawler import Crawler
from .exeptions import LNException


def __format_title(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().title()


def __synopsis_fallback(crawler: Crawler) -> str:
    soup = getattr(crawler, "last_soup", None)
    if soup is None:
        return ""
    for selector in (
        'meta[property="og:description"]',
        'meta[name="description"]',
        'meta[property="twitter:description"]',
    ):
        tag = soup.select_one(selector)
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def __format_volume(crawler: Crawler, vol_id_map: Dict[int, int]) -> None:
    if crawler.volumes:
        crawler.volumes = [
            vol if isinstance(vol, Volume) else Volume(**vol)
            for vol in sorted(crawler.volumes, key=lambda x: x.get("id"))
        ]
    else:
        chapter_volumes = sorted(
            {
                chap.get("volume")
                for chap in crawler.chapters
                if isinstance(chap.get("volume"), int) and chap.get("volume") > 0
            }
        )
        if chapter_volumes:
            crawler.volumes = [Volume(id=vol_id, title="") for vol_id in chapter_volumes]

    for index, vol in enumerate(crawler.volumes):
        if not isinstance(vol.id, int) or vol.id < 0:
            raise LNException(f"Invalid volume id at index {index}")
        vol.title = __format_title(vol.title or f"Volume {vol.id}")
        vol.start_chapter = len(crawler.chapters)
        vol.final_chapter = 0
        vol.chapter_count = 0
        vol_id_map[vol.id] = index


def __format_chapters(crawler: Crawler, vol_id_map: Dict[int, int]) -> None:
    crawler.chapters = [
        chap if isinstance(chap, Chapter) else Chapter(**chap)
        for chap in sorted(crawler.chapters, key=lambda x: x.get("id"))
    ]
    for index, item in enumerate(crawler.chapters):
        if not isinstance(item.id, int) or item.id < 0:
            raise LNException(f"Unknown item id at index {index}")

        if isinstance(item.get("volume"), int):
            vol_index = vol_id_map.get(item.volume, -1)
        else:
            vol_index = -1

        if 0 <= vol_index < len(crawler.volumes):
            volume = crawler.volumes[vol_index]
            item.volume = volume.id
            item.volume_title = volume.title
            volume.start_chapter = min(volume.start_chapter, item.id)
            volume.final_chapter = max(volume.final_chapter, item.id)
            volume.chapter_count += 1
        else:
            item.volume = 0
            item.volume_title = ""

        item.title = re.sub(r"\s+", " ", str(item.title or f"#{item.id}")).strip()


def format_novel(crawler: Crawler) -> None:
    crawler.novel_title = __format_title(crawler.novel_title)
    crawler.novel_author = __format_title(crawler.novel_author)
    if not crawler.novel_synopsis:
        crawler.novel_synopsis = __synopsis_fallback(crawler)
    vol_id_map: Dict[int, int] = {}
    __format_volume(crawler, vol_id_map)
    __format_chapters(crawler, vol_id_map)
    crawler.volumes = [x for x in crawler.volumes if x["chapter_count"] > 0]


def save_metadata(app, completed: bool = False) -> None:
    from .app import App

    if not (isinstance(app, App) and isinstance(app.crawler, Crawler)):
        return

    crawler = app.crawler
    meta = MetaInfo(
        novel=Novel(
            url=crawler.novel_url,
            title=crawler.novel_title,
            authors=[x.strip() for x in crawler.novel_author.split(",") if x.strip()],
            cover_url=crawler.novel_cover,
            synopsis=crawler.novel_synopsis,
            language=crawler.language,
            novel_tags=crawler.novel_tags,
            volumes=crawler.volumes,
            chapters=[Chapter.without_body(chap) for chap in crawler.chapters],
            is_rtl=crawler.is_rtl,
            has_manga=crawler.has_manga,
            has_mtl=crawler.has_mtl,
            # Optional metadata: sources may populate these; the DB importer
            # reads them when present.
            status=getattr(crawler, "status", None) or NovelStatus.unknown,
            editors=getattr(crawler, "editors", None) or [],
            translators=getattr(crawler, "translators", None) or [],
            novelupdates_url=getattr(crawler, "novelupdates_url", None),
            original_publisher=getattr(crawler, "original_publisher", None),
            english_publisher=getattr(crawler, "english_publisher", None),
            genres=getattr(crawler, "genres", None) or [],
            tags=getattr(crawler, "tags", None) or [],
            description=getattr(crawler, "description", None),
            language_code=getattr(crawler, "language_code", None) or [],
            source=getattr(crawler, "source", None),
        ),
        session=Session(
            completed=completed,
            user_input=app.user_input,
            output_path=app.output_path,
            output_formats=app.output_formats,
            pack_by_volume=app.pack_by_volume,
            good_file_name=app.good_file_name,
            download_chapters=[chap.id for chap in app.chapters],
            cookies=app.crawler.cookies,
            headers=app.crawler.headers,
            proxies={},
        ),
    )

    try:
        Path(app.output_path).mkdir(parents=True, exist_ok=True)
        file_name = Path(app.output_path) / META_FILE_NAME
        with open(file_name, "w", encoding="utf-8") as fp:
            json.dump(meta.to_dict(), fp, ensure_ascii=False, indent=2)
    except Exception:
        pass
