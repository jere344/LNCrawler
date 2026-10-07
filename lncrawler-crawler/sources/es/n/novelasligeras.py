# -*- coding: utf-8 -*-
"""novelasligeras.net — "NOVA", the largest Spanish light-novel site.

Hard Cloudflare block
---------------------
Every path (and the WordPress REST API) answers this host with a Cloudflare
*managed* challenge (HTTP 403, "Just a moment..."), as signed by
``window._cf_chl_opt.cType = 'managed'``. The native curl_cffi backend cannot
clear it, and headless Chromium (Playwright, no stealth) stays on the challenge
page and earns no ``cf_clearance`` cookie, so a browser fallback buys nothing.
The site is registered but hidden until the challenge is lifted.

The parser targets the WooCommerce/"Wolf" theme the site historically used and
follows the upstream lightnovel-crawler source, so it can be re-enabled once
access is restored.
"""

import logging
import re
from typing import List
from urllib.parse import quote, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.models import Chapter, SearchResult, Volume

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://novelasligeras.net/?post_type=product&title=1&excerpt=1&content=0"
    "&categories=1&attributes=1&tags=1&sku=0&orderby=title-DESC&ixwps=1&s={query}"
)


class NovelasLigerasCrawler(Crawler):
    base_url = [
        "https://novelasligeras.net/",
        "https://www.novelasligeras.net/",
    ]
    language = "es"

    is_disabled = True
    disable_reason = (
        "Cloudflare managed challenge (HTTP 403 'Just a moment...') on every "
        "path, including the WordPress REST API. Native curl_cffi cannot clear "
        "it and headless Chromium stays on the challenge, so it needs a "
        "residential proxy / solving service."
    )

    def initialize(self) -> None:
        self.cleaner.bad_text_regex.update(["Publicidad"])
        self.cleaner.bad_css.update(["div[style]"])

    def search_novel(self, query: str) -> List[SearchResult]:
        soup = self.get_soup(SEARCH_URL.format(query=quote(query)))
        results = []
        for cell in soup.select(".wf-cell[data-post-id]"):
            link = cell.select_one(".alignnone")
            if not link:
                continue
            rating = cell.select_one(".star-rating")
            results.append(
                SearchResult(
                    title=(cell.get("data-name") or "").strip(),
                    url=self.absolute_url(link["href"]),
                    info="Clasificación: %s"
                    % (rating.get("aria-label") if rating else "N/A"),
                )
            )
        return results

    def read_novel_info(self) -> None:
        soup = self.get_soup(self.novel_url)

        title = soup.select_one("h1.product_title")
        assert title, "Sin título"
        self.novel_title = title.get_text(" ", strip=True)

        author = soup.select_one(
            'tr.woocommerce-product-attributes-item--attribute_pa_escritor a'
        )
        if author:
            self.novel_author = author.get_text(" ", strip=True)

        cover = soup.select_one('meta[property="og:image"]')
        if cover and cover.get("content"):
            self.novel_cover = self.absolute_url(cover["content"])

        synopsis = soup.select_one(".woocommerce-product-details__short-description")
        if synopsis:
            self.novel_synopsis = synopsis.get_text(" ", strip=True)

        host = urlparse(self.novel_url).hostname or ""
        pattern = re.escape(host) + r"/index.php/\d{4}/\d{2}/\d{2}/"
        volume_pattern = r"-volumen-(\d+)-"

        last_vol_id = 0
        count = 0
        for a in soup.select(
            ".wpb_wrapper a:not([id],[title],[href$='suscripciones/'],"
            "[href*='patreon'],[href*='paypal'])"
        ):
            if not re.search(pattern, a["href"]):
                continue
            count += 1

            match = re.search(volume_pattern, a["href"])
            vol_id = int(match.group(1)) if match else last_vol_id
            last_vol_id = vol_id
            if vol_id and not any(v["id"] == vol_id for v in self.volumes):
                self.volumes.append(Volume(id=vol_id, title=f"Volumen {vol_id}"))

            chapter_title = re.sub(r"\bCapitulo\b", "Capítulo", a.get_text(" ", strip=True))
            if "Parte" in chapter_title and "Capítulo" in chapter_title:
                chapter_title = " – ".join(chapter_title.split(" – ")[::-1])

            self.chapters.append(
                Chapter(
                    id=count,
                    title=chapter_title,
                    url=self.absolute_url(a["href"]),
                    volume=vol_id,
                )
            )

    def download_chapter_body(self, chapter: Chapter) -> str:
        soup = self.get_soup(chapter.url)
        body = soup.select_one(".wpb_text_column > div:nth-child(1)")
        if body is None:
            return ""
        return self.cleaner.extract_contents(body)
