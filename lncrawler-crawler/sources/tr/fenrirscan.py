# -*- coding: utf-8 -*-
import json
import logging
import re
from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class FenrirScans(Crawler):
    base_url = ["https://fenrirscans.com/"]
    search_url = "https://fenrirscans.com/wp-admin/admin-ajax.php"
    has_manga = False
    has_mtl = False

    def _starlab_ajax(self, soup):
        # The StarLab theme exposes its AJAX url + nonce in a starlab_ajax object.
        match = re.search(r"starlab_ajax\s*=\s*(\{.*?\});", str(soup), re.S)
        if not match:
            return self.search_url, ""
        data = json.loads(match.group(1))
        return data.get("ajax_url", self.search_url), data.get("nonce", "")

    def search_novel(self, query):
        """
        Uses the site's live search AJAX endpoint to find novels.
        """
        # Swap: old ts_ac_do_search action (removed) -> StarLab live_search_novels
        soup = self.get_soup(self.base_url[0])
        ajax_url, nonce = self._starlab_ajax(soup)
        data = {
            "action": "live_search_novels",
            "search_term": query,
            "post_type": "novel",
            "nonce": nonce,
        }
        response = self.post_response(ajax_url, data=data)
        novels = []
        try:
            results = response.json()["data"]["results"]
        except Exception:
            return novels
        for item in results:
            title = item.get("title")
            url = item.get("link")
            if title and url:
                novels.append(
                    {
                        "title": title,
                        "url": self.absolute_url(url),
                    }
                )
        return novels

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup("https://fenrirscans.com/rankings/")
        results = []
        for item in soup.select(
            "#rk-panel-weekly li.rk-podium-item, #rk-panel-weekly li.rk-row"
        ):
            a = item.select_one(".rk-podium-title a, a.rk-row-title, .rk-row-title a")
            if not a:
                continue
            results.append(
                SearchResult(
                    title=a.get_text(strip=True),
                    url=self.absolute_url(a["href"]),
                )
            )
        return results[offset : offset + limit]

    def read_novel_info(self):
        """
        Parses novel metadata and chapter list from the novel page.
        """
        soup = self.get_soup(self.novel_url)
        # Metadata
        title = soup.find("h1")
        if title:
            self.novel_title = title.text.strip()

        # Synopsis
        summary = soup.select_one(
            ".novel-description, .description-full, .description-short"
        )
        if summary:
            self.novel_synopsis = self.cleaner.extract_contents(summary)

        # Cover
        cover = soup.find("img", {"class": "wp-post-image"})
        if cover:
            self.novel_cover = self.absolute_url(cover.get("src"))
        # Tags/Genres
        for tag in soup.select(".novel-genres-main a, .genre-tag-main"):
            self.novel_tags.append(tag.text.strip())

        # Author
        author = soup.select_one(".novel-author, .author-link")
        if author:
            self.novel_author = author.text.replace("Yazar:", "").strip()

        # Chapters are lazy-loaded: pull them from the theme's AJAX endpoint.
        ajax_url, nonce = self._starlab_ajax(soup)
        novel_match = re.search(r'data-novel-id="(\d+)"', str(soup)) or re.search(
            r"postid-(\d+)", str(soup)
        )
        if not novel_match:
            return
        novel_id = novel_match.group(1)

        page = 1
        while True:
            response = self.post_response(
                ajax_url,
                data={
                    "action": "get_all_novel_chapters",
                    "novel_id": novel_id,
                    "page": page,
                    "nonce": nonce,
                },
            )
            try:
                data = response.json()["data"]
            except Exception:
                break
            for item in data.get("chapters", []):
                self.chapters.append(
                    {
                        "id": len(self.chapters) + 1,
                        "volume": 1,
                        "url": self.absolute_url(item["value"]),
                        "title": item["text"],
                    }
                )
            if not data.get("has_more") or page >= data.get("total_pages", page):
                break
            page += 1

    def download_chapter_body(self, chapter):
        """
        Downloads the body of a single chapter.
        """
        soup = self.get_soup(chapter["url"])
        # Theme update: content moved from #readerarea to .chapter-content
        content = soup.select_one(".chapter-content") or soup.select_one(
            ".chapter-content-wrapper"
        )
        if not content:
            logger.error("No content found for chapter: %s", chapter["url"])
            return None
        return self.cleaner.extract_contents(content)
