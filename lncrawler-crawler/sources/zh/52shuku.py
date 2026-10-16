# -*- coding: utf-8 -*-
"""52书库 (www.52shuku.net) - Chinese web novel library, static HTML.

Book pages are <name>.html. Each book is split into reader pages <name>_N.html,
where the table of contents links point to _2 (first page) through _(count+1)
(last page). Each reader page is one chapter entry, titled "第N页".
Search: /so/search.php?q=<keyword>&p=<page>. Ranking: /nan/TuiJian.html (Top 200).
Bodies are in article.article-content; scripts and ad blocks are stripped.
"""

import logging
import re
from html import escape
from urllib.parse import quote

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume

logger = logging.getLogger(__name__)

SITE = "https://www.52shuku.net"
PAGE_RE = re.compile(r"_(\d+)\.html$")
CHAPTER_MARK = re.compile(r"第[\d一二三四五六七八九十百千]+章")
PROMO_RE = re.compile(
    r"^(上一页|下一页|目录|首页|尾页)$"
    r"|^(?=.{0,120}$).*(52shuku|52书库|本站).*(收藏|推荐|网址|来源)"
    r"|^(?=.{0,120}$).*52shuku\.net"
)


class Shuku52Crawler(Crawler):
    base_url = [
        "https://www.52shuku.net",
    ]
    language = "zh"
    has_mtl = False

    def search_novel(self, query):
        """Site search, paginated with &p=N; stops when a page adds nothing new."""
        results = []
        seen = set()
        for page in range(1, 21):
            soup = self.get_soup(f"{SITE}/so/search.php?q={quote(query)}&p={page}")
            found = 0
            for a in soup.select("article.excerpt header h2 a[href]"):
                url = self.absolute_url(a["href"])
                if not url or url in seen:
                    continue
                seen.add(url)
                found += 1
                title = re.sub(r"^\d+\.\s*", "", a.get_text(strip=True))
                results.append(SearchResult(title=title, url=url, info=""))
            if not found:
                break
        return results

    def browse_novels(self, offset=0, limit=50):
        """Top 200 ranking from /nan/TuiJian.html (single page, sliced by offset/limit)."""
        soup = self.get_soup(f"{SITE}/nan/TuiJian.html")
        results = []
        seen = set()
        for h3 in soup.select("article ul h3"):
            a = h3.select_one("a[href]")
            if not a:
                continue
            url = self.absolute_url(a["href"])
            if not url or url in seen:
                continue
            seen.add(url)
            title = a.get_text(strip=True)
            info = h3.get_text(" ", strip=True).replace(title, "")
            info = re.sub(r"^\d+、\s*", "", info).strip()
            results.append(SearchResult(title=title, url=url, info=info))
        return results[offset : offset + limit]

    def read_novel_info(self):
        """Title, author, status, synopsis, cover and the reader-page chapter list."""
        # Normalize any reader-page URL (book_N.html) to the book page (book.html).
        self.novel_url = re.sub(r"_\d+\.html$", ".html", self.novel_url)
        logger.info("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        h1 = soup.select_one("h1")
        raw_title = h1.get_text(strip=True) if h1 else ""
        assert raw_title, "No novel title found"

        # Titles look like "书名_作者【完结】".
        name, _, tail = raw_title.partition("_")
        self.novel_title = name.strip() or raw_title
        tail_plain = re.sub(r"【[^】]*】", "", tail).strip()

        container = soup.select_one("article.article-content")
        text = container.get_text("\n", strip=True) if container else ""
        text = text.replace("　", " ")
        syn_text = self._synopsis_text(text)

        author_match = re.search(r"作者[：:]\s*([^\s【：:]+)", syn_text or text)
        if tail_plain:
            self.novel_author = tail_plain
        elif author_match:
            self.novel_author = author_match.group(1).strip()

        if "完结" in raw_title or "完結" in raw_title or "完结" in text[:300]:
            self.status = NovelStatus.completed
        elif "连载" in raw_title or "連載" in raw_title or "连载" in text[:300]:
            self.status = NovelStatus.ongoing
        else:
            self.status = NovelStatus.unknown

        if syn_text:
            self.novel_synopsis = syn_text

        og = soup.select_one("meta[property='og:image']")
        if og and og.get("content"):
            self.novel_cover = self.absolute_url(og["content"])

        logger.info("Getting chapters...")
        page_nums = []
        for a in soup.select("ul.list li.mulu a[href]"):
            m = PAGE_RE.search(a["href"])
            if m:
                page_nums.append(int(m.group(1)))
        assert page_nums, "No reader pages found in table of contents"

        base = self.novel_url[: -len(".html")]
        last = max(page_nums)
        volume_chapters = list(range(2, last + 1))
        self.volumes = [
            Volume(
                id=1,
                start_chapter=1,
                final_chapter=len(volume_chapters),
                chapter_count=len(volume_chapters),
            )
        ]
        for idx, n in enumerate(volume_chapters, 1):
            self.chapters.append(
                Chapter(
                    id=idx,
                    title=f"第{idx}页",
                    url=f"{base}_{n}.html",
                    volume=1,
                )
            )
        logger.info("Found %d chapters", len(self.chapters))

    @staticmethod
    def _synopsis_text(text):
        """Intro block before the first chapter heading or promo footer."""
        cut = len(text)
        m = CHAPTER_MARK.search(text)
        if m:
            cut = min(cut, m.start())
        j = text.find("本站内容来源")
        if j != -1:
            cut = min(cut, j)
        head = text[:cut]
        head = re.sub(r"^\s*小说简介[：:]\s*", "", head)
        lines = [l.strip() for l in head.split("\n") if l.strip()]
        return "\n".join(lines)

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        body = soup.select_one("article.article-content")
        if not body:
            logger.warning("Chapter body not found: %s", chapter.url)
            return ""
        for tag in body.select(
            "script, style, ins, iframe, noscript, .adsbygoogle, div.txtad, [class*='advert']"
        ):
            tag.decompose()

        parts = []
        for s in body.stripped_strings:
            s = s.replace("　", " ").strip()
            if not s or PROMO_RE.search(s):
                continue
            parts.append(s)
        return "".join(f"<p>{escape(p)}</p>" for p in parts)
