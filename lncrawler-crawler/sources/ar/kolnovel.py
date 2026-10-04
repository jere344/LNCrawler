import logging

from lncrawl.models import SearchResult
from lncrawl.templates.mangastream import MangaStreamTemplate

logger = logging.getLogger(__name__)


class Kolnovel(MangaStreamTemplate):
    has_mtl = False
    has_manga = False
    base_url = ["https://kolnovel.com/"]

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            url = "https://kolnovel.com/series/?order=popular"
            if page > 1:
                url = f"https://kolnovel.com/series/?order=popular&page={page}"
            soup = self.get_soup(url)
            items = soup.select(".listupd > article")
            if not items:
                break
            for item in items:
                a = item.select_one("h2 a")
                if not a:
                    continue
                results.append(
                    SearchResult(
                        title=a.get_text(strip=True),
                        url=self.absolute_url(a["href"]),
                    )
                )
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]

    def parse_genres(self, soup):
        for a in soup.select(".sertogenre a[href*='/genre/']"):
            yield a.text.strip()

    def parse_authors(self, soup):
        for a in soup.select(".sertoauth a[href*='/writer/']"):
            yield a.text.strip()

    def parse_title(self, soup):
        title = super().parse_title(soup)
        for row in soup.select(".serl"):
            label = row.select_one(".sername")
            if label and "اللغة الأم" in label.get_text():
                value = row.select_one(".serval")
                if value and value.get_text(strip=True):
                    self.alternative_titles = [value.get_text(strip=True)]
                break
        return title

    def select_chapter_tags(self, tag):
        # kolnovel lists a `/pdf` download link next to every real chapter in
        # `.eplister`; those stubs have no body, so skip them.
        for a in super().select_chapter_tags(tag):
            if not a.get("href", "").rstrip("/").endswith("/pdf"):
                yield a
