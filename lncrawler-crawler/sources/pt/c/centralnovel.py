# -*- coding: utf-8 -*-
"""Central Novel (pt-BR).

The task description called this a Madara site, but the live markup and the
2022 Wayback snapshots show the WordPress **MangaStream** theme instead
(``.listupd > article``, ``.eplister li a``, ``h1.entry-title``,
``.entry-content`` for both synopsis and chapter body), so this subclasses
:class:`MangaStreamTemplate`.

The site is currently fronted by a hard Cloudflare managed challenge
("Just a moment..." / Turnstile): native curl_cffi and both headless and
headful Playwright receive HTTP 403 and never receive the clearance cookie
(verified from this host). It is therefore registered but disabled.
"""

from bs4 import BeautifulSoup

from lncrawl.templates.mangastream import MangaStreamTemplate


class CentralNovelCrawler(MangaStreamTemplate):
    base_url = [
        "https://centralnovel.com/",
        "https://www.centralnovel.com/",
    ]
    language = "pt"

    is_disabled = True
    disable_reason = (
        "Cloudflare managed challenge (Turnstile) returns 403 to native "
        "requests and never clears in headless/headful Playwright."
    )

    def parse_genres(self, soup: BeautifulSoup):
        for a in soup.select(".genxed a[href*='/genre/']"):
            text = a.get_text(strip=True)
            if text:
                yield text

    def parse_summary(self, soup: BeautifulSoup) -> str:
        for node in soup.select(".entry-content"):
            text = self.cleaner.extract_contents(node)
            if text:
                return text
        return ""
