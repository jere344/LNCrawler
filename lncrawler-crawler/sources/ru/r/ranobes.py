# -*- coding: utf-8 -*-
import logging
import re

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class RanobesComCrawler(Crawler):
    base_url = "https://ranobes.com/"
    language = "ru"

    def search_novel(self, query):
        soup = self.submit_form_for_soup(
            self.home_url,
            data={"do": "search", "subaction": "search", "story": query},
            headers={"Referer": self.home_url},
        )
        results = []
        seen = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not re.match(r"^https?://ranobes\.com/ranobe/\d+", href) or href in seen:
                continue
            seen.add(href)
            results.append({"title": a.get_text(strip=True), "url": href})
        return results

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        desc = soup.select_one('meta[property="og:title"]')
        if desc:
            self.novel_title = desc.get("content", "").strip()
        if not self.novel_title:
            h1 = soup.select_one("h1")
            self.novel_title = h1.get_text(strip=True) if h1 else ""
        logger.info("Novel title: %s", self.novel_title)

        authors = [a.get_text(strip=True) for a in soup.select('a[href*="/authors/"]')]
        if authors:
            self.novel_author = ", ".join(authors)
        logger.info("Novel author: %s", self.novel_author)

        synopsis = soup.select_one('meta[property="og:description"]')
        if synopsis:
            self.novel_synopsis = synopsis.get("content", "")
        logger.info("Novel synopsis: %s", self.novel_synopsis)

        toc_url = None
        for a in soup.select("a[href]"):
            if re.match(r"^https?://ranobes\.com/chapters/[^/]+/$", a.get("href", "")):
                toc_url = a["href"]
                break
        if not toc_url:
            return

        slug = toc_url.rstrip("/").split("/")[-1]
        pattern = re.compile(r"/chapters/%s/\d+-" % re.escape(slug))
        date_re = re.compile(r"\d{1,2} \S+ \d{4} в \d{1,2}:\d{2}$")
        seen = set()
        entries = []
        page = 1
        while page <= 300:
            url = toc_url if page == 1 else "%spage/%d/" % (toc_url, page)
            try:
                page_soup = self.get_soup(url)
            except Exception:
                break
            links = [
                (a.get_text(strip=True), a["href"])
                for a in page_soup.select("a[href]")
                if pattern.search(a["href"]) and a["href"] not in seen
            ]
            if not links:
                break
            for title, href in links:
                seen.add(href)
                entries.append((date_re.sub("", title).strip(), href))
            page += 1

        for title, href in reversed(entries):
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "title": title,
                    "url": href,
                }
            )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        title = soup.select_one("h1")
        if title:
            chapter["title"] = title.get_text(strip=True)
        contents = soup.select_one("article .text") or soup.select_one(".text")
        self.cleaner.clean_contents(contents)
        return str(contents)
