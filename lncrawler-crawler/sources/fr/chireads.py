# -*- coding: utf-8 -*-

import logging
import re
from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class Chireads(Crawler):
    base_url = ["https://chireads.com/"]
    has_manga = False
    has_mtl = False

    def search_novel(self, query):
        query = query.lower().replace(" ", "+")

        # Swap: requests.get + make_soup -> crawler get_soup helper
        soup = self.get_soup("https://chireads.com/search?x=0&y=0&name=" + query)

        result = []
        content = soup.find("div", {"id": "content"})

        for novel in content.find_all("li"):
            content = novel.find("a")
            result.append(
                {
                    "title": content.get("title"),
                    "url": self.absolute_url(content.get("href")),
                    "cover": self.image_url(novel.find("img")),
                }
            )

        return result

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            url = "https://chireads.com/category/translatedtales/"
            if page > 1:
                url += f"page/{page}/"
            soup = self.get_soup(url)
            items = soup.select("article")
            if not items:
                break
            for item in items:
                a = item.select_one("h2 a[href]")
                if not a:
                    continue
                results.append(
                    SearchResult(
                        title=a.get_text(" ", strip=True),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)
        # Site redesigned: the container is now <main class="conteiner"> using
        # refresh-detail-* classes instead of the old div/inform-* markup.
        content = soup.select_one("main.conteiner") or soup.select_one("div.conteiner")
        metadata = content.select_one(".refresh-detail-hero-copy")

        summary = content.select_one(".refresh-detail-summary-content")
        if summary:
            self.novel_synopsis = self.cleaner.extract_contents(summary)

        for tag in content.select(".refresh-detail-tags a"):
            self.novel_tags.append(tag.text.strip())

        cover = content.select_one(".refresh-detail-cover img")
        if cover:
            self.novel_cover = self.absolute_url(cover.get("src"))

        # The title cell holds the French title followed by alternative titles,
        # separated by " | " (novel 0) or " / " (novel 1).
        title_parts = re.split(
            r"\s+[|/]\s+", metadata.select_one(".refresh-detail-title").text.strip()
        )
        self.novel_title = title_parts[0].strip()
        self.alternative_titles = [x.strip() for x in title_parts[1:] if x.strip()]

        for row in content.select(".refresh-detail-meta > div"):
            dt = row.select_one("dt")
            dd = row.select_one("dd")
            if dt and dd and "Auteur" in dt.text:
                self.novel_author = dd.text.strip()
                break

        # "Traducteur" (or "Fantrad" for fan translations). The Fantrad cell can
        # also hold "Check : <name>" after a "|", which is the proofreader.
        translators = []
        for row in content.select(".refresh-detail-meta > div"):
            dt = row.select_one("dt")
            dd = row.select_one("dd")
            if not (dt and dd):
                continue
            label = dt.text.strip()
            if "Traduc" in label or "Fantrad" in label:
                for part in dd.text.split("|"):
                    part = part.strip()
                    if part.lower().startswith("check"):
                        self.editors = [part.split(":", 1)[-1].strip()]
                    elif part:
                        translators.append(part)
        if translators:
            self.translators = translators

        # Chapters are grouped into tome (volume) segments. Each segment is a
        # <button aria-controls="refresh-detail-volume-N"> whose text holds the
        # tome title, followed by a <div class="refresh-detail-segment-panel">
        # with its own <ul class="refresh-detail-chapter-list">.
        seen = set()
        segments = content.select(".refresh-detail-segment-panel")
        if segments:
            groups = []
            for vol_id, segment in enumerate(segments, start=1):
                title = ""
                panel_id = segment.get("id")
                if panel_id:
                    button = content.select_one(
                        'button[aria-controls="%s"]' % panel_id
                    )
                    span = button.select_one("span") if button else None
                    if span:
                        title = span.get_text(" ", strip=True)
                self.volumes.append({"id": vol_id, "title": title})
                groups.append(
                    (vol_id, segment.select(".refresh-detail-chapter-list a"))
                )
        else:
            self.volumes.append({"id": 1, "title": ""})
            groups = [(1, content.select(".refresh-detail-chapter-list a"))]

        for vol_id, anchors in groups:
            for chapter in anchors:
                url = self.absolute_url(chapter.get("href"))
                if url in seen:
                    continue
                seen.add(url)
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "volume": vol_id,
                        "url": url,
                        "title": (chapter.get("title") or chapter.text)
                        .replace("\xa0", " ")
                        .strip(),
                    }
                )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        content = soup.find(
            "div",
            {
                "id": "content",
                "class": "font-color-black3 article-font",
            },
        )
        return self.cleaner.extract_contents(content)
