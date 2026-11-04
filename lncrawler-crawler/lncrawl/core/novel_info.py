import json
import re
from pathlib import Path
from typing import Dict

from ..constants import META_FILE_NAME
from ..models import Chapter, MetaInfo, Novel, NovelStatus, Session, Volume
from .crawler import Crawler
from .exeptions import LNException


# Volume/part numbers such as II or XIV; L/C/D/M are left out so words like MIX or DID are not kept upper.
ROMAN_NUMERAL_RE = re.compile(r"[IVX]+")
# Initials such as "J.K." stay upper case.
INITIALS_RE = re.compile(r"(?:[^\W\d_]\.)+[^\W\d_]?")
TITLE_QUOTES = "'\"‘’“”"
# An apostrophe inside a word ("don't") or opening a contraction ("'tis") keeps the next letter lower.
TITLE_APOSTROPHES = "'’"
# Single-case titles get a capital after these too, e.g. "RE:ZERO" -> "Re:Zero".
TITLE_SEGMENT_RE = re.compile(r"(?<=[ :\-/(])")
TITLE_EDGE_PUNCT = "()[]{}.,:;!?-–—" + TITLE_QUOTES

# Site boilerplate that meta descriptions use in place of a real synopsis. The
# read-online and free-online phrases only count at the start: real blurbs use them too.
SYNOPSIS_BOILERPLATE_RE = re.compile(
    r"^\s*read\b.{0,80}\b(online|for free)|^\s*(free online|latest chapters?)"
    r"|novel online|light novel online|在线阅读|免费阅读|最新章节|全文阅读|無料で読める",
    re.IGNORECASE,
)
# Longer texts are real blurbs that may mention these phrases in passing.
BOILERPLATE_MAX_LENGTH = 300
MIN_SYNOPSIS_LENGTH = 40
# Mostly-CJK text carries more meaning per character, so a shorter blurb still counts.
MIN_CJK_SYNOPSIS_LENGTH = 15
CJK_CHAR_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]")


def __title_segment(segment: str) -> str:
    core = segment.strip(TITLE_EDGE_PUNCT)
    if ROMAN_NUMERAL_RE.fullmatch(core):
        return segment
    if INITIALS_RE.fullmatch(segment.strip("()[]{},:;!?-–—" + TITLE_QUOTES)):
        return segment.upper()
    lower = segment.lower()
    for index, ch in enumerate(lower):
        # An ordinal or a number-led word ("2nd", "4th") takes no capital.
        if ch.isdigit():
            break
        if ch.isalpha():
            # Letter after an apostrophe inside a word, or after a leading "'" ("'tis").
            if index and lower[index - 1] in TITLE_APOSTROPHES and (index == 1 or lower[index - 2].isalpha()):
                break
            return lower[:index] + ch.upper() + lower[index + 1 :]
    return lower


def __title_word(word: str) -> str:
    return "".join(__title_segment(seg) for seg in TITLE_SEGMENT_RE.split(word) if seg)


def __format_title(text) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    has_upper = any(ch.isupper() for ch in text)
    has_lower = any(ch.islower() for ch in text)
    # Mixed case is deliberate (e.g. "CosmicChaos", "Don't"): keep it as written.
    # Only single-case text, or text with no cased letters at all, is re-cased.
    if has_upper == has_lower:
        return text
    return " ".join(__title_word(word) for word in text.split(" "))


def __normalise_text(text: str) -> str:
    return re.sub(r"\W", "", text.lower())


def __min_synopsis_length(text: str) -> int:
    letters = [ch for ch in text if ch.isalpha()]
    cjk = sum(1 for ch in letters if CJK_CHAR_RE.match(ch))
    return MIN_CJK_SYNOPSIS_LENGTH if cjk * 2 > len(letters) else MIN_SYNOPSIS_LENGTH


def __is_junk_synopsis(text: str, title: str) -> bool:
    """True when a meta description is the title, site boilerplate or too short."""
    if len(text) < __min_synopsis_length(text):
        return True
    norm = __normalise_text(text)
    if not norm or norm in title or (title and title in norm and len(title) >= 0.8 * len(norm)):
        return True
    return len(text) < BOILERPLATE_MAX_LENGTH and bool(SYNOPSIS_BOILERPLATE_RE.search(text))


def __synopsis_fallback(crawler: Crawler) -> str:
    soup = getattr(crawler, "last_soup", None)
    if soup is None:
        return ""
    title = __normalise_text(str(crawler.novel_title or ""))
    for selector in (
        'meta[property="og:description"]',
        'meta[name="description"]',
        'meta[property="twitter:description"]',
    ):
        tag = soup.select_one(selector)
        if not (tag and tag.get("content")):
            continue
        text = tag["content"].strip()
        if not __is_junk_synopsis(text, title):
            return text
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


def __split_values(value, separators: str) -> list:
    """Normalize a str-or-list field into a de-duplicated list of strings."""
    if not value:
        return []
    parts = value if not isinstance(value, str) else re.split(separators, value)
    result = []
    for item in parts:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def __format_tags(crawler: Crawler) -> None:
    """Expose genres as tags: merge novel_tags + genres + tags into one list."""
    merged = []
    for value in (
        getattr(crawler, "novel_tags", None),
        getattr(crawler, "genres", None),
        getattr(crawler, "tags", None),
    ):
        for tag in __split_values(value, r"[,;/|\n]+"):
            if tag not in merged:
                merged.append(tag)
    crawler.novel_tags = merged


def format_novel(crawler: Crawler) -> None:
    crawler.novel_title = __format_title(crawler.novel_title)
    crawler.novel_author = __format_title(crawler.novel_author)
    if not crawler.novel_synopsis:
        crawler.novel_synopsis = __synopsis_fallback(crawler)
    __format_tags(crawler)
    crawler.alternative_titles = __split_values(
        getattr(crawler, "alternative_titles", None), r"[\n;]+"
    )
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
            alternative_titles=getattr(crawler, "alternative_titles", None) or [],
            volumes=crawler.volumes,
            chapters=[Chapter.without_body(chap) for chap in crawler.chapters],
            is_rtl=crawler.is_rtl,
            has_manga=crawler.has_manga,
            has_mtl=crawler.has_mtl,
            is_adult=getattr(crawler, "is_adult", False),
            # Optional metadata: sources may populate these; the DB importer
            # reads them when present.
            status=getattr(crawler, "status", None) or NovelStatus.unknown,
            editors=getattr(crawler, "editors", None) or [],
            translators=getattr(crawler, "translators", None) or [],
            novelupdates_url=getattr(crawler, "novelupdates_url", None),
            edition=getattr(crawler, "novel_edition", "") or None,
            original_publisher=getattr(crawler, "original_publisher", None),
            english_publisher=getattr(crawler, "english_publisher", None),
            genres=getattr(crawler, "genres", None) or [],
            tags=getattr(crawler, "tags", None) or [],
            source=getattr(crawler, "source", None),
            source_version=getattr(crawler, "version", 1),
        ),
        session=Session(
            completed=completed,
            user_input=app.user_input,
            output_path=app.output_path,
            good_file_name=app.good_file_name,
            download_chapters=[chap.id for chap in app.chapters],
        ),
    )

    try:
        Path(app.output_path).mkdir(parents=True, exist_ok=True)
        file_name = Path(app.output_path) / META_FILE_NAME
        with open(file_name, "w", encoding="utf-8") as fp:
            json.dump(meta.to_dict(), fp, ensure_ascii=False)
    except Exception:
        pass
