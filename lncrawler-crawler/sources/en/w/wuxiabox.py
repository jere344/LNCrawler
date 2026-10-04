import logging

from lncrawl.templates.novelmtl import NovelMTLTemplate

logger = logging.getLogger(__name__)


class Wuxiabox(NovelMTLTemplate):
    has_mtl = True
    has_manga = False
    base_url = ["https://www.wuxiabox.com/"]

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
