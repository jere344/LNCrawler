import logging

from lncrawl.models import SearchResult
from lncrawl.templates.mangastream import MangaStreamTemplate

logger = logging.getLogger(__name__)


class CkandawritesOnline(MangaStreamTemplate):
    has_mtl = False
    has_manga = False
    base_url = ["https://ckandawrites.online/"]

    def initialize(self) -> None:
        super().initialize()
        # The site's bot check blocks curl_cffi's default chrome TLS
        # fingerprint but lets firefox through.
        self.scraper.impersonate = "firefox"

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(f"{self.home_url}series/?page={page}")
            items = soup.select(".listupd article")
            if not items:
                break
            for item in items:
                a = item.select_one("h2 a[href]") or item.select_one("a.tip[href]")
                if not a:
                    continue
                title = (a.get("title") or a.text).strip()
                if not title:
                    continue
                results.append(
                    SearchResult(title=title, url=self.absolute_url(a["href"]))
                )
            page += 1
            if page > 200:
                break
        return results[offset : offset + limit]

