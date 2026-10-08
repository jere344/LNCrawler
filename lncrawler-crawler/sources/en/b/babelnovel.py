# -*- coding: utf-8 -*-
import json
import logging
from urllib.parse import quote, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)

babelnovel_api = 'https://api.babelnovel.com'
login_url = babelnovel_api + '/v1/user-account/web-login'
search_url = babelnovel_api + '/v1/books?page=0&pageSize=8&fields=id,name,canonicalName,lastChapter&ignoreStatus=false&query=%s'
novel_page_url = babelnovel_api + '/v1/books/%s'
chapter_list_url = babelnovel_api + '/v1/books/%s/chapters?bookId=%s&page=%d&pageSize=100&fields=id,name,canonicalName,isBought,isFree,isLimitFree'
chapter_json_url = babelnovel_api + '/v1/books/%s/chapters/%s/content'
chapter_page_url = 'https://babelnovel.com/books/%s/chapters/%s'


class BabelNovelCrawler(Crawler):
    base_url = ['https://babelnovel.com/',
                'https://api.babelnovel.com']

    def initialize(self):
        self.home_url = 'https://babelnovel.com/'

    def login(self, email, password):
        logger.info('Visiting %s', self.home_url)
        data = self.post_json(login_url, data=json.dumps({
            'loginType': 'web',
            'password': password,
            'userName': email,
        }), headers={
            'Content-Type': 'application/json;charset=UTF-8',
        })

        self.token = data['data']['loginResult']['token']
        self.set_header('token', self.token)

        self.user_id = data['data']['loginResult']['user']['id']
        self.set_header('x-user-id', self.user_id)
        logger.info('User ID = %s', self.user_id)

    def search_novel(self, query):
        # to get cookies
        self.get_response(self.home_url)

        url = search_url % quote(query.lower())
        logger.debug('Visiting: %s', url)
        data = self.get_json(url)

        results = []
        for item in data['data']:
            if not item['canonicalName']:
                continue

            info = None
            if item['lastChapter']:
                info = 'Latest: %s' % item['lastChapter']['name']

            results.append({
                'title': item['name'],
                'url': novel_page_url % item['canonicalName'],
                'info': info,
            })

        return results

    def browse_novels(self, offset=0, limit=50):
        soup = self.get_soup(self.home_url + "ranking")
        results = []
        seen = set()
        for a in soup.select("a[href^='/books/']"):
            url = self.absolute_url(a["href"])
            if url in seen:
                continue
            img = a.select_one("img[alt]")
            title = (img.get("alt") if img else "") or a.get_text(" ", strip=True)
            if not title.strip():
                continue
            seen.add(url)
            results.append(SearchResult(title=title.strip(), url=url))
        return results[offset : offset + limit]

    def read_novel_info(self):
        # Determine cannonical novel name
        path_fragments = urlparse(self.novel_url.rstrip('/')).path.split('/')
        if path_fragments[1] == 'books':
            self.novel_hash = path_fragments[2]
        else:
            self.novel_hash = path_fragments[-1]

        self.novel_url = novel_page_url % self.novel_hash
        logger.info('Canonical name: %s', self.novel_hash)

        logger.debug('Visiting %s', self.novel_url)
        data = self.get_json(self.novel_url)

        self.novel_author = data['data']['author']['enName']
        logger.info('Novel author: %s', self.novel_author)

        self.novel_id = data['data']['id']
        logger.info('Novel ID: %s', self.novel_id)

        self.novel_title = data['data']['name']
        logger.info('Novel title: %s', self.novel_title)

        self.novel_cover = data['data']['cover']
        logger.info('Novel cover: %s', self.novel_cover)

        self.novel_synopsis = data['data'].get('synopsis') or ''
        logger.info('Novel synopsis: %s', self.novel_synopsis)

        self.genres = [
            g['engName'] for g in data['data'].get('genres') or [] if g.get('engName')
        ]
        self.novel_tags = [
            tag for tag in (data['data'].get('tag') or '').split('|') if tag
        ]
        logger.info('Novel tags: %s', self.novel_tags)

        cn_name = data['data'].get('cnName')
        if cn_name and cn_name != self.novel_title:
            self.alternative_titles = [cn_name]

        chapter_count = int(data['data']['releasedChapterCount'])
        self.get_list_of_chapters(chapter_count)

    def get_list_of_chapters(self, chapter_count):
        calls = []
        for page in range(1 + chapter_count // 100):
            list_url = chapter_list_url % (self.novel_id, self.novel_id, page)
            calls.append((self.parse_chapter_item, list_url))

        for page, chapters in enumerate(self.resolve_bounded(calls)):
            self.volumes.append({'id': page + 1})
            for chap in chapters:
                chap['volume'] = page + 1
                chap['id'] = 1 + len(self.chapters)
                self.chapters.append(chap)

    def parse_chapter_item(self, list_url):
        logger.debug('Visiting %s', list_url)
        data = self.get_json(list_url)
        chapters = list()
        for item in data['data']:
            if not (item['isFree'] or item['isLimitFree'] or item['isBought']):
                continue

            chapters.append({
                'title': item['name'],
                'url': chapter_page_url % (self.novel_hash, item['canonicalName']),
                'json_url': chapter_json_url % (self.novel_hash, item['id']),
            })

        return chapters

    def download_chapter_body(self, chapter):
        data = self.get_json(chapter['json_url'])
        soup = self.make_soup(data['data']['content'].replace('\n', '<br>'))
        body = soup.find('body')
        return self.cleaner.extract_contents(body)
