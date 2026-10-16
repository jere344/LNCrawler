# -*- coding: utf-8 -*-
import logging
import re
from time import sleep, time
from urllib.parse import quote_plus, urlparse

from lncrawl.core.crawler import Crawler
from lncrawl.models import SearchResult

logger = logging.getLogger(__name__)


class WattpadCrawler(Crawler):
    base_url = [
        "https://www.wattpad.com/",
        "https://my.w.tt/",
    ]

    def initialize(self):
        self.home_url = "https://www.wattpad.com/"

    def search_novel(self, query):
        # The API returns a serialized PHP array instead of JSON when the
        # request carries the JSON Accept header, so force a plain one.
        for _ in range(3):
            try:
                data = self.get_json(
                    f"{self.home_url}api/v3/stories?fields=stories(id,title,url)"
                    f"&query={quote_plus(query)}&limit=10",
                    headers={"Accept": "*/*"},
                )
                return [
                    {"title": s["title"], "url": s["url"]}
                    for s in data["stories"]
                ]
            except Exception:
                sleep(1)
        return []

    def browse_novels(self, offset=0, limit=50):
        results = []
        url = f"{self.home_url}api/v3/stories?fields=stories(id,title,url)&limit=50&filter=hot"
        page = 0
        while url and len(results) < offset + limit and page < 40:
            data = self.get_json(url, headers={"Accept": "*/*"})
            stories = data.get("stories") or []
            if not stories:
                break
            for story in stories:
                results.append(
                    SearchResult(title=story["title"], url=story["url"])
                )
            url = data.get("nextUrl")
            page += 1
        return results[offset : offset + limit]

    def login(self, email: str, password: str) -> None:
        resp = self.submit_form(
            f"{self.home_url}login?nextUrl=/home",
            data={
                "username": email,
                "password": password,
            },
        )
        apiAuthKey = re.findall(r"wattpad\.apiAuthKey = '([^']+)';", resp.text)
        if not apiAuthKey:
            raise Exception("Failed to login")
        logger.info("authorization", apiAuthKey[0])
        self.set_header("authorization", apiAuthKey[0])

        data = self.get_json(
            f"{self.home_url}api/v3/internal/current_user?fields=email,username,name",
        )
        logger.debug("current user", data)
        if email.lower() != data["username"].lower():
            raise Exception("Failed to login")
        print(
            "Logged in as %s[%s]<%s>" % (data["name"], data["username"], data["email"])
        )

    def read_novel_info(self):
        search_id = re.compile(r"(\d+)")
        id_no = search_id.search(self.novel_url)
        response = self.get_response(f"{self.home_url}api/v3/stories/{id_no.group()}")
        story_info = response.json()

        self.novel_title = story_info["title"]
        logger.info("Novel title: %s", self.novel_title)

        self.novel_synopsis = story_info.get("description") or ""
        logger.info("Novel synopsis length: %s", len(self.novel_synopsis))

        self.novel_tags = list(story_info.get("tags") or [])
        logger.info("Novel tags: %s", self.novel_tags)

        self.novel_cover = self.absolute_url(story_info["cover"])
        logger.info("Novel cover: %s", self.novel_cover)

        self.novel_author = story_info["user"]["name"]
        logger.info("Novel author: %s", self.novel_author)

        for a in story_info["parts"]:
            self.chapters.append(
                {
                    "id": len(self.chapters) + 1,
                    "url": self.absolute_url(a["url"]),
                    "title": a["title"],
                }
            )

    def download_chapter_body(self, chapter):
        chapter_id = urlparse(chapter["url"]).path.split("-")[0].strip("/")
        info_url = f"{self.home_url}v4/parts/{chapter_id}?fields=id,title,pages,text_url&_={int(time() * 1000)}"

        logger.info("Getting info %s", info_url)
        response = self.get_response(info_url)
        data = response.json()
        chapter["title"] = data["title"]
        text_url = data["text_url"]["text"]

        logger.info("Getting text %s", text_url)
        response = self.get_response(text_url)
        text = response.content.decode("utf8")
        text = re.sub(r'<p data-p-id="[a-f0-9]+>"', "<p>", text)
        return text
