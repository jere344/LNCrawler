# -*- coding: utf-8 -*-
import html
import logging
import re
from urllib.parse import quote_plus

from lncrawl.core import body_migrations
from lncrawl.core.crawler import Crawler
from lncrawl.models import NovelStatus, SearchResult

logger = logging.getLogger(__name__)

_STATUSES = {
    "ongoing": NovelStatus.ongoing,
    "completed": NovelStatus.completed,
    "hiatus": NovelStatus.hiatus,
}

clear = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
crypt = "rhbndjzvqkiexcwsfpogytumalVUQXWSAZKBJNTLEDGIRHCPFOMY"

decrypt_table = dict(zip(clear, crypt))


def decrypt_string(crypted_string):
    return ''.join(map(lambda c: decrypt_table.get(c, c),
                       list(crypted_string)))


class SecondLifeTransCrawler(Crawler):
    base_url = 'https://secondlifetranslations.com/'
    version = 2
    body_migrations = {2: "_migrate_v2"}

    def initialize(self):
        # The "Support <translator> on Ko-fi" call-to-action block at the end of some chapters.
        self.cleaner.bad_css.update(['.jmbl-disclaimer', '.wp-block-buttons'])

    def search_novel(self, query):
        data = self.get_json(
            f"{self.base_url[0]}/wp-json/wp/v2/novel"
            f"?search={quote_plus(query)}&per_page=10"
        )
        return [
            {"title": item["title"]["rendered"], "url": item["link"]}
            for item in data
        ]

    def browse_novels(self, offset=0, limit=50):
        results = []
        page = 1
        while len(results) < offset + limit:
            data = self.get_json(
                f"{self.home_url}wp-json/wp/v2/novel?per_page=100&page={page}"
            )
            if not isinstance(data, list) or not data:
                break
            for item in data:
                results.append(
                    SearchResult(
                        title=item["title"]["rendered"],
                        url=item["link"],
                    )
                )
            page += 1
        return results[offset : offset + limit]

    def read_novel_info(self):
        soup = self.get_soup(self.novel_url)

        self.novel_title = (soup.select_one('meta[property="og:title"]')
                            ['content'])

        possible_cover = soup.select_one('meta[property="og:image"]')
        if possible_cover:
            self.novel_cover = self.absolute_url(possible_cover['content'])

        logger.info('Novel cover: %s', self.novel_cover)

        novelcontent = soup.select_one(".novelcontent")
        if novelcontent:
            author_strong = novelcontent.find('strong', string='Author: ')
            if author_strong and author_strong.next_sibling:
                self.novel_author = author_strong.next_sibling.text

        logger.info('Novel author: %s', self.novel_author)

        self.novel_tags = [
            a.text.strip() for a in soup.select('.novelgenres a')
        ]
        logger.info('Novel tags: %s', self.novel_tags)
        self.is_adult = 'Adult' in self.novel_tags

        # "Label:" lines followed by their value, e.g. "Translation Status:" / "Ongoing".
        lines = []
        if novelcontent:
            lines = novelcontent.get_text('\n', strip=True).split('\n')
        fields = {}
        for label, value in zip(lines, lines[1:]):
            if label.endswith(':') and not value.endswith(':'):
                fields.setdefault(label[:-1].lower(), value)

        self.status = _STATUSES.get(
            fields.get('translation status', '').lower(), NovelStatus.unknown
        )
        raw_title = fields.get('raw title & source', '')
        if raw_title:
            self.alternative_titles = [raw_title]

        # The summary block holds the blurb, a "Synopsis:" label, a tag line and
        # sometimes the translator's note; only the blurb paragraphs are kept.
        summary = soup.select_one('div.novel-entry-content')
        if summary:
            paragraphs = []
            for p in summary.find_all('p'):
                text = p.get_text(' ', strip=True)
                if not text or (text.endswith(':') and len(text) < 40) or re.match(r'(tags?|translators?)\b', text, re.I):
                    continue
                paragraphs.append(f'<p>{html.escape(text, quote=False)}</p>')
            self.novel_synopsis = ''.join(paragraphs)

        volumes = soup.select('button.accordion')
        for vol_id, volume in enumerate(volumes, 1):
            self.volumes.append({'id': vol_id, 'title': volume.text})

            for a in volume.next_sibling.select('div > div > a'):
                chap_id = 1 + len(self.chapters)

                self.chapters.append({
                    'id': chap_id,
                    'volume': vol_id,
                    'title': a.text.strip(),
                    'url': self.absolute_url(a['href']),
                })

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter['url'])
        contents = soup.select_one('.entry-content.clr')
        for span in contents.select('span.jmbl'):
            span.string = decrypt_string(span.text)

        return self.cleaner.extract_contents(contents)

    def _migrate_v2(self, body, chapter):
        return body_migrations.drop_matching(body, r"^Support .{1,40} on Ko-fi$", max_length=60)
