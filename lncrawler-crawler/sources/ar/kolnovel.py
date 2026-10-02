import logging

from lncrawl.templates.mangastream import MangaStreamTemplate

logger = logging.getLogger(__name__)


class Kolnovel(MangaStreamTemplate):
    has_mtl = False
    has_manga = False
    base_url = ["https://kolnovel.com/"]

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
