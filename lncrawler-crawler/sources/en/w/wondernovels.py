# -*- coding: utf-8 -*-
import logging
import re
from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)
search_url = "https://wondernovels.com/?s=%s&post_type=wp-manga"


class WonderNovels(Crawler):
    base_url = "https://wondernovels.com/"

    def search_novel(self, query):
        query = query.lower().replace(" ", "+")
        soup = self.get_soup(search_url % query)

        results = []
        for tab in soup.select(".c-tabs-item__content"):
            a = tab.select_one(".post-title h3 a")
            if not a:
                continue
            latest = tab.select_one(".latest-chap .chapter a")
            votes = tab.select_one(".rating .total_votes")
            results.append(
                {
                    "title": a.text.strip(),
                    "url": self.absolute_url(a["href"]),
                    "info": " | ".join(
                        x.text.strip() for x in (latest, votes) if x
                    ),
                }
            )

        return results

    def browse_novels(self, offset: int = 0, limit: int = 50):
        results = []
        page = 1
        while len(results) < offset + limit:
            url = self.home_url if page == 1 else "%spage/%d/" % (self.home_url, page)
            try:
                soup = self.get_soup(url, params={"m_orderby": "views"})
            except Exception:
                break
            items = soup.select(".page-item-detail")
            if not items:
                break
            for tab in items:
                a = tab.select_one(".post-title h3 a")
                if not a:
                    continue
                results.append(
                    SearchResult(
                        title=a.text.strip(),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        possible_title = soup.select_one(".post-title h1")
        for span in possible_title.select("span"):
            span.extract()
        self.novel_title = possible_title.text.strip()
        logger.info("Novel title: %s", self.novel_title)

        cover = soup.select_one(".summary_image a img") or soup.select_one(
            ".summary_image img"
        )
        if cover:
            self.novel_cover = self.absolute_url(
                cover.get("data-src") or cover.get("src")
            )
        logger.info("Novel cover: %s", self.novel_cover)

        self.novel_author = " ".join(
            [
                a.text.strip()
                for a in soup.select('.author-content a[href*="translator"]')
            ]
        )
        if not self.novel_author:
            author = soup.select_one('.post-content_item h5:-soup-contains("Author")')
            if author:
                content = author.find_next_sibling()
                if content:
                    self.novel_author = content.get_text(strip=True)
            else:
                match = re.search(
                    r'"author"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"',
                    str(soup),
                )
                if match:
                    self.novel_author = match.group(1)
        logger.info("Novel author: %s", self.novel_author)

        self.genres = [
            a.get_text(strip=True)
            for a in soup.select(".genres-content a[rel='tag']")
            if a.get_text(strip=True)
        ]
        self.tags = [
            a.get_text(strip=True)
            for a in soup.select(".tags-content a[rel='tag']")
            if a.get_text(strip=True)
        ]
        logger.info("Novel genres: %s", self.genres)
        logger.info("Novel tags: %s", self.tags)

        item = None
        for node in soup.select(".post-content_item"):
            heading = node.select_one(".summary-heading h5")
            content = node.select_one(".summary-content")
            if not heading or not content:
                continue
            if "alternative" in heading.get_text(strip=True).lower():
                item = content
                break
        if item:
            self.alternative_titles = [
                part.strip()
                for part in re.split(r"\n|,", item.get_text(" ", strip=True))
                if part.strip()
            ]
        logger.info("Alternative titles: %s", self.alternative_titles)

        synopsis_tag = soup.select_one(".summary__content")
        if synopsis_tag:
            self.novel_synopsis = self.cleaner.extract_contents(synopsis_tag)
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        clean_novel_url = self.novel_url.split("?")[0].rstrip("/")
        response = self.submit_form(
            f"{clean_novel_url}/ajax/chapters/",
            headers={
                "x-requested-with": "XMLHttpRequest",
                "referer": self.novel_url,
            },
        )
        soup = self.make_soup(response)
        for a in reversed(soup.select(".wp-manga-chapter a")):
            chap_id = len(self.chapters) + 1
            vol_id = 1 + len(self.chapters) // 100
            if chap_id % 100 == 1:
                self.volumes.append({"id": vol_id})
            self.chapters.append(
                {
                    "id": chap_id,
                    "volume": vol_id,
                    "title": a.text.strip(),
                    "url": self.absolute_url(a["href"]),
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select(".reading-content p")
        return "".join([str(p) for p in contents])
