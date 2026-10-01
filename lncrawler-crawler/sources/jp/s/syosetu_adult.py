# -*- coding: utf-8 -*-
import logging
from urllib.parse import quote_plus

from bs4 import element

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)

# Adult (R18) branch of the Narou engine. The reading domain is novel18.syosetu.com;
# nocturne/moonlight are the (redirecting) portal hostnames kept for URL matching.
search_url = "https://noc.syosetu.com/search/search/?word=%s"


class SyosetuAdultCrawler(Crawler):
    has_mtl = True
    base_url = [
        "https://novel18.syosetu.com/",
        "https://nocturne.syosetu.com/",
        "https://moonlight.syosetu.com/",
    ]
    language = "ja"

    def initialize(self) -> None:
        # The R18 reading domain gates content behind an age cookie.
        self.set_cookie("over18", "yes")

    def search_novel(self, query):
        soup = self.get_soup(search_url % quote_plus(query))
        results = []
        for tab in soup.select(".searchkekka_box"):
            a = tab.select_one(".novel_h a")
            if not a:
                continue
            latest = tab.select_one(".left")
            results.append(
                {
                    "title": a.text.strip(),
                    "url": self.absolute_url(a["href"]),
                    "info": latest.get_text(" ", strip=True) if latest else "",
                }
            )
        return results

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        self.novel_title = soup.select_one(".p-novel__title").text.strip()
        logger.debug("Novel title: %s", self.novel_title)

        author_tag = soup.select_one(".p-novel__author") or soup.select_one(
            ".novel_writername a"
        )
        if author_tag:
            self.novel_author = (
                author_tag.get_text(strip=True).replace("作者：", "").strip()
            )

        synopsis_tag = soup.select_one(".p-novel__summary") or soup.select_one(
            "#novel_ex"
        )
        if synopsis_tag:
            self.novel_synopsis = synopsis_tag.get_text("\n", strip=True)

        soups = [soup]
        pager_last = soup.select_one(".c-pager__item--last")
        if pager_last and "href" in pager_last.attrs:
            page_num = int(pager_last["href"].split("=")[-1])
            soups += [self.get_soup(f"{self.novel_url}?p={x}") for x in range(2, page_num + 1)]

        volume_id = 0
        chapter_id = 0
        self.volumes.append({"id": 0})
        for page in soups:
            for tag in page.select_one(".p-eplist"):
                if type(tag) is element.NavigableString:
                    continue
                if "p-eplist__chapter-title" in tag.attrs.get("class", ""):
                    volume_id += 1
                    self.volumes.append({"id": volume_id, "title": tag.text.strip()})
                else:
                    link = tag.select("a")
                    if not link:
                        continue
                    link = link[0]
                    chapter_id += 1
                    self.chapters.append(
                        {
                            "id": chapter_id,
                            "volume": volume_id,
                            "title": link.text.strip(),
                            "url": self.absolute_url(link["href"]),
                        }
                    )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".p-novel__body")
        return self.cleaner.extract_contents(contents)
