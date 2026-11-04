from bs4 import Tag

from lncrawl.core import body_migrations
from lncrawl.templates.novelmtl import NovelMTLTemplate

# Taboola widget call leaked as bare text in a <p>.
_TABOOLA = "_taboola"


class WuxiaSpotCrawler(NovelMTLTemplate):
    has_mtl = False
    has_manga = False
    base_url = "https://www.wuxiaspot.com/"
    version = 2
    body_migrations = {2: "_migrate_v2"}

    def parse_chapter_body(self, tag):
        if isinstance(tag, Tag):
            for p in tag.select("p"):
                if _TABOOLA in p.get_text():
                    p.decompose()
        return super().parse_chapter_body(tag)

    def _migrate_v2(self, body, chapter):
        return body_migrations.drop_matching(body, _TABOOLA)

    def browse_novels(self, offset: int = 0, limit: int = 50):
        results = []
        page = 0
        while len(results) < offset + limit:
            soup = self.get_soup(
                "%slist/all/all-onclick-%d.html" % (self.home_url, page)
            )
            items = soup.select("ul.novel-list .novel-item a")
            if not items:
                break
            for a in items:
                results.append(self.parse_search_item(a))
            page += 1
            if page > 40:
                break
        return results[offset : offset + limit]
