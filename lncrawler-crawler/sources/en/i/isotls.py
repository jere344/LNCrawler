# -*- coding: utf-8 -*-
import logging
import re
from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class IsotlsCrawler(Crawler):
    base_url = [
        'https://isotls.com/',
        'https://www.isotls.com/',
    ]

    def search_novel(self, query):
        soup = self.get_soup(f"{self.base_url[0]}/novels/")
        query = query.lower()
        results = []
        for a in soup.select("a[href]"):
            href = a["href"].split("?")[0]
            if not re.match(r"^/novel/[0-9a-f]+/?$", href):
                continue
            title = a.text.strip()
            if title and query in title.lower():
                results.append({"title": title, "url": self.absolute_url(href)})
        return results[:10]

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(f"{self.home_url}novels/")
        results = []
        for a in soup.select("a[href]"):
            href = a["href"].split("?")[0]
            if not re.match(r"^/novel/[0-9a-f]+/?$", href):
                continue
            title = a.text.strip()
            if not title:
                continue
            results.append(SearchResult(title=title, url=self.absolute_url(href)))
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        possible_cover = soup.select_one('img.novel-cover') or soup.select_one(
            'meta[property="og:image"]'
        )
        if possible_cover:
            self.novel_cover = self.absolute_url(
                possible_cover.get('src') or possible_cover.get('content')
            )

        possible_title = soup.select_one('meta[property="og:title"]')
        assert possible_title, 'No novel title'
        self.novel_title = possible_title['content']

        possible_novel_author = soup.select_one('meta[name="twitter:data1"]')
        if possible_novel_author:
            self.novel_author = possible_novel_author['content']

        synopsis = soup.select_one('#synopsis .flow-md') or soup.select_one('#synopsis')
        if synopsis:
            self.novel_synopsis = self.cleaner.extract_contents(synopsis)

        for a in soup.select('main section:nth-child(3) nav ul li a'):
            chap_id = len(self.chapters) + 1
            vol_id = len(self.chapters) // 100 + 1
            if len(self.chapters) % 100 == 0:
                self.volumes.append({'id': vol_id})

            self.chapters.append({
                'id': chap_id,
                'volume': vol_id,
                'title': a.text.strip(),
                'url': self.absolute_url(a['href']),
            })

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter['url'])
        contents = soup.select_one("div.content")
        return self.cleaner.extract_contents(contents)
