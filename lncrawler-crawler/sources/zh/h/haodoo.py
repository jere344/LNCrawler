# -*- coding: utf-8 -*-
"""好讀書櫃 (haodoo.net) - Traditional Chinese classics and modern literature, static HTML.

Book pages are ?M=book&P=<id>. A book has one or more volumes, each opened by a
ReadOnline('<volid>', 'book') button. The reader is ?M=u&P=<volid>:<N>&L=book:
N=0 is the table of contents, N=1..maxChapterID are the chapters. Text lives in
<pre id="SourceText"> with U+3000 indents; pages are UTF-8. Listings are
?M=hd&P=<category>-<page>, with audio and Share entries mixed in (both skipped).
Search is client-side Google CSE with no server endpoint, so search_novel returns [].
"""

import logging
import re
from html import escape

from bs4 import NavigableString

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

SITE = "https://haodoo.net"
BOOK_ID_RE = re.compile(r"M=book&P=([0-9A-Za-z]+)")
READ_ONLINE_RE = re.compile(r"ReadOnline\('([^']+)',\s*'book'\)")
SET_TITLE_RE = re.compile(r"SetTitle\(\"([^\"]+)\"\)")
MAX_ID_RE = re.compile(r"maxChapterID\s*=\s*(\d+)")
CHAPTER_HEAD_RE = re.compile(r"第[〇○零一二三四五六七八九十百千萬\d]+回")
CHAPTER_HEAD_START_RE = re.compile(r"^\s*" + CHAPTER_HEAD_RE.pattern)
PAGE_NUM_RE = re.compile(r"^第\s*\d+。?$")
PAGE_PREFIX_RE = re.compile(r"^第\s*\d+。\s*")
FRONT_MATTER_RE = re.compile(r"^\s*︽|^\s*好讀書櫃")
ENDING_RE = re.compile(r"完結|完结")
# Red-font candidates for the author fallback: site UI (search box) and reader comment dates.
AUTHOR_REJECT_RE = re.compile(r"google|搜尋|[\s-]", re.IGNORECASE)
AUTHOR_MAX_LEN = 20

# Listing categories, walked in order by browse_novels.
BROWSE_CATEGORIES = [
    "100",
    "martial",
    "wisdom",
    "history",
    "mystery",
    "romance",
    "scifi",
    "fiction",
]
MAX_BROWSE_PAGES = 30
MAX_VOLUMES = 50
MAX_CHAPTERS = 500


class HaodooCrawler(Crawler):
    base_url = [
        "https://haodoo.net/",
    ]
    language = "zh"
    has_mtl = False

    def search_novel(self, query):
        """Not supported: haodoo.net search runs client-side (Google CSE) and has no
        server endpoint to query, so this returns an empty list without any request."""
        return []

    def browse_novels(self, offset=0, limit=50):
        """Walk the category listings in order, skipping audio and Share entries,
        deduplicated by series id. Stops once offset+limit results are collected."""
        need = offset + limit
        results = []
        seen = set()
        for cat in BROWSE_CATEGORIES:
            # The previous page is held back until the next page confirms it is real.
            held, held_ids = [], set()
            for page in range(1, MAX_BROWSE_PAGES + 1):
                if len(results) >= need:
                    return results[offset:offset + limit]
                entries = self._listing_entries(cat, page)
                ids = {sid for sid, _ in entries}
                # Past the last page the site repeats one generic listing. If this page
                # matches the held one, the held page is that generic copy: drop it.
                if ids and ids == held_ids:
                    held = []
                    break
                self._add_entries(entries=held, cat=cat, results=results, seen=seen)
                held, held_ids = entries, ids
                if not ids:
                    break
            else:
                # Page cap reached with nothing to compare against; keep the last page.
                self._add_entries(entries=held, cat=cat, results=results, seen=seen)
        return results[offset:offset + limit]

    def _listing_entries(self, cat, page):
        """(series id, title) for each book link on one listing page; audio is skipped."""
        soup = self.get_soup(f"{SITE}/?M=hd&P={cat}-{page}")
        entries = []
        for a in soup.select("a[href]"):
            m = BOOK_ID_RE.search(a["href"])
            if not m or m.group(1).startswith("audio"):
                continue
            title = a.get_text(strip=True).strip("【】《》").strip()
            if title:
                entries.append((m.group(1), title))
        return entries

    @staticmethod
    def _add_entries(entries, cat, results, seen):
        for sid, title in entries:
            if sid in seen:
                continue
            seen.add(sid)
            results.append(
                SearchResult(
                    title=title,
                    url=f"{SITE}/?M=book&P={sid}",
                    info=f"category {cat}",
                )
            )

    def read_novel_info(self):
        """Title, author, synopsis, tags, cover, status and the chapter list
        (one reader table of contents per volume)."""
        m = BOOK_ID_RE.search(self.novel_url)
        if m:
            self.novel_url = f"{SITE}/?M=book&P={m.group(1)}"
        book_id = m.group(1) if m else self.novel_url
        logger.info("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        # The title is set by an inline script as SetTitle("作者【书名】").
        m = SET_TITLE_RE.search(str(soup))
        assert m, "No title found"
        raw = m.group(1).strip()
        if "【" in raw:
            author, _, rest = raw.partition("【")
            title = rest.rstrip("】").strip()
        else:
            author, title = "", raw
        self.novel_title = title or raw
        author = author.strip() or self._author_fallback(soup)
        if author:
            self.novel_author = author

        lines = [l.strip() for l in soup.get_text("\n", strip=True).split("\n")]
        syn = self._synopsis_lines(lines)
        if syn:
            self.novel_synopsis = "".join(f"<p>{escape(p, quote=False)}</p>" for p in syn)
        self.novel_tags = ["世紀百強"] if "世紀百強" in lines else []

        if ENDING_RE.search(" ".join(lines)):
            self.status = NovelStatus.completed

        img = soup.select_one("img[src*='covers/']")
        if img and img.get("src"):
            self.novel_cover = self.absolute_url(img["src"])

        logger.info("Getting volumes and chapters...")
        volumes = []
        seen = set()
        for btn in soup.select("input[onclick]"):
            m = READ_ONLINE_RE.search(btn.get("onclick", ""))
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            volumes.append((m.group(1), self._volume_label(btn)))
        assert volumes, "No volumes found"
        if len(volumes) > MAX_VOLUMES:
            logger.warning(
                "Book %s: dropping %d volumes beyond MAX_VOLUMES=%d",
                book_id,
                len(volumes) - MAX_VOLUMES,
                MAX_VOLUMES,
            )

        self.volumes = []
        self.chapters = []
        chapter_seen = set()
        for volid, label in volumes[:MAX_VOLUMES]:
            vol_id = len(self.volumes) + 1
            max_id, toc = self._read_toc(volid, book_id)
            if max_id <= 0:
                logger.warning("No chapters found for volume %s", volid)
                continue

            # Prefer the TOC lines when they line up one-to-one with the chapter ids.
            titles = toc if len(toc) == max_id else [l for l in toc if CHAPTER_HEAD_RE.search(l)]
            if len(titles) != max_id:
                titles = []

            start = len(self.chapters) + 1
            for n in range(1, max_id + 1):
                url = f"{SITE}/?M=u&P={volid}:{n}&L=book"
                if url in chapter_seen:
                    continue
                chapter_seen.add(url)
                if titles:
                    title = titles[n - 1]
                else:
                    title = self._title_from_body(url)
                self.chapters.append(
                    Chapter(
                        id=len(self.chapters) + 1,
                        title=title or f"Chapter {n}",
                        url=url,
                        volume=vol_id,
                    )
                )

            count = len(self.chapters) - start + 1
            if count <= 0:
                continue
            self.volumes.append(
                Volume(
                    id=vol_id,
                    title=label or f"Volume {vol_id}",
                    start_chapter=start,
                    final_chapter=start + count - 1,
                    chapter_count=count,
                )
            )
        assert self.chapters, "No chapters found"
        logger.info("Found %d chapters in %d volumes", len(self.chapters), len(self.volumes))

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        pre = soup.select_one("pre#SourceText")
        if not pre:
            logger.warning("No reader body in %s", chapter["url"])
            return ""

        parts = []
        leading = True
        for line in pre.get_text("\n").split("\n"):
            line = line.replace("　", " ").strip()
            if not line:
                continue
            # Drop the ︽…︾ banner and the 好讀書櫃 credit that open the first chapter.
            if leading and FRONT_MATTER_RE.search(line):
                continue
            leading = False
            line = self.cleaner.clean_text(line)
            if line:
                parts.append(f"<p>{escape(line, quote=False)}</p>")
        return "".join(parts)

    def _read_toc(self, volid, book_id):
        """Return (maxChapterID, non-empty TOC lines) from the volume's reader page N=0."""
        soup = self.get_soup(f"{SITE}/?M=u&P={volid}:0&L=book")
        m = MAX_ID_RE.search(str(soup))
        found = int(m.group(1)) if m else 0
        max_id = min(found, MAX_CHAPTERS)
        if found > MAX_CHAPTERS:
            logger.warning(
                "Book %s, volume %s: dropping %d chapters beyond MAX_CHAPTERS=%d",
                book_id,
                volid,
                found - MAX_CHAPTERS,
                MAX_CHAPTERS,
            )
        toc = []
        pre = soup.select_one("pre#SourceText")
        if pre:
            for line in pre.get_text("\n").split("\n"):
                # Collapse U+3000 and spaces; some TOC headings have a stray space before 回.
                line = re.sub(r"\s*(?=回)", "", " ".join(line.split()))
                if line:
                    toc.append(line)
        return max_id, toc

    def _title_from_body(self, url):
        """Fallback chapter title: the first 第…回 heading in the reader body."""
        soup = self.get_soup(url)
        pre = soup.select_one("pre#SourceText")
        if pre:
            for line in pre.get_text("\n").split("\n"):
                line = " ".join(line.split())
                if CHAPTER_HEAD_START_RE.search(line):
                    return line
        return ""

    @staticmethod
    def _author_fallback(soup):
        """First red <font> on the page that looks like a name; on this layout it holds the author.
        Red fonts also carry site UI (e.g. 搜尋好讀 - Google) and comment dates, which are rejected."""
        for font in soup.find_all("font"):
            text = font.get_text(strip=True)
            if (font.get("color") or "").upper() != "CC0000" or not text:
                continue
            if len(text) > AUTHOR_MAX_LEN or AUTHOR_REJECT_RE.search(text):
                continue
            return text
        return ""

    @staticmethod
    def _volume_label(btn):
        """The volume name is the nearest text node before its ReadOnline button, e.g. 《射鵰英雄傳一》."""
        for sib in btn.previous_siblings:
            if isinstance(sib, NavigableString):
                text = sib.strip()
                if text:
                    return text.strip("《》").strip()
        return ""

    @staticmethod
    def _synopsis_lines(lines):
        """Paragraphs after the 名列 (ranking) line, up to the errata (勘誤表) block."""
        start = next((i + 1 for i, l in enumerate(lines) if "名列" in l), None)
        if start is None:
            return []
        out = []
        for line in lines[start:]:
            if "勘誤表" in line or FRONT_MATTER_RE.search(line):
                break
            # A page marker can share its line with the next label (第 26。作者 …).
            line = PAGE_PREFIX_RE.sub("", line).strip()
            if not line or PAGE_NUM_RE.match(line) or line == "世紀百強":
                continue
            out.append(line)
        return out
