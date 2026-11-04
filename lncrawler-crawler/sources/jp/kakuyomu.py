# -*- coding: utf-8 -*-
import json
import logging
import re
from typing import Generator, Union

from bs4 import BeautifulSoup, Tag

from lncrawl.core.exeptions import LNException
from lncrawl.models import Chapter, NovelStatus, SearchResult, Volume
from lncrawl.templates.soup.general import GeneralSoupTemplate
from lncrawl.templates.soup.searchable import SearchableSoupTemplate

logger = logging.getLogger(__name__)


class KakuyomuCrawler(SearchableSoupTemplate, GeneralSoupTemplate):
    base_url = "https://kakuyomu.jp/"
    language = "ja"

    def initialize(self) -> None:
        self.init_executor()

    # -- search -------------------------------------------------------- #

    def select_search_items(self, query: str) -> Generator[Tag, None, None]:
        soup = self.get_soup(f"{self.home_url}search?q={query}")
        seen = set()
        for a in soup.select('a[href^="/works/"]'):
            href = a["href"]
            if not re.fullmatch(r"/works/\d+", href):
                continue
            if href in seen:
                continue
            seen.add(href)
            yield a

    def parse_search_item(self, tag: Tag) -> SearchResult:
        title = tag.get_text(" ", strip=True)
        heading = tag.find_previous("h3")
        if heading:
            title = heading.get_text(" ", strip=True)
        return SearchResult(title=title, url=self.absolute_url(tag["href"]))

    def browse_novels(self, offset=0, limit=50):
        results = []
        seen = set()
        page = 1
        while len(results) < offset + limit:
            soup = self.get_soup(
                f"{self.home_url}rankings/all/entire?work_variation=all&page={page}"
            )
            added = 0
            for a in soup.select("h3 a[href*=works]"):
                href = a.get("href", "")
                if not re.fullmatch(r"/works/\d+", href):
                    continue
                url = self.absolute_url(href)
                if url in seen:
                    continue
                seen.add(url)
                results.append(
                    SearchResult(title=a.get_text(" ", strip=True), url=url)
                )
                added += 1
            if not added:
                break
            page += 1
        return results[offset : offset + limit]

    # -- novel info ---------------------------------------------------- #

    def read_novel_info(self) -> None:
        super().read_novel_info()
        self.novel_edition = "Web Novel"
        self.status = NovelStatus.unknown
        soup = self.last_soup
        if isinstance(soup, BeautifulSoup):
            # Serialization state is a meta item such as "連載中 全 773 話".
            for item in soup.select('[class*="Meta_metaItem"]'):
                text = item.get_text(" ", strip=True)
                if text.startswith("連載中"):
                    self.status = NovelStatus.ongoing
                    break
                if text.startswith("完結"):
                    self.status = NovelStatus.completed
                    break

    def parse_title(self, soup: BeautifulSoup) -> str:
        tag = soup.select_one("h1")
        assert isinstance(tag, Tag)
        return tag.get_text(strip=True)

    def parse_cover(self, soup: BeautifulSoup) -> str:
        # og:image is kakuyomu's generated share card (title text and the site
        # logo), not the book cover. The real cover is in the page state.
        _, work = self._work_state(soup)
        return work.get("adminCoverImageUrl") or ""

    def parse_authors(self, soup: BeautifulSoup):
        tag = soup.select_one('[class*="WorkAuthorBox"] a[href^="/users/"]')
        if isinstance(tag, Tag):
            yield tag.get_text(strip=True)

    def parse_genres(self, soup: BeautifulSoup):
        seen = set()
        for a in soup.select('a[href^="/genres/"]'):
            text = a.get_text(strip=True)
            if text and text not in seen:
                seen.add(text)
                yield text

    def parse_summary(self, soup: BeautifulSoup) -> str:
        # The introduction is the collapsible block; WorkIntroduction holds only the catchphrase.
        tag = soup.select_one('[class*="CollapseTextWithKakuyomuLinks_collapseText"]')
        if isinstance(tag, Tag):
            return self.cleaner.extract_contents(tag)
        return ""

    def _work_state(self, soup: BeautifulSoup) -> tuple:
        # The work page embeds its whole state (table of contents included)
        # in __NEXT_DATA__; the rendered TOC only shows the first rows.
        cached = getattr(self, "_work_cache", None)
        if cached is not None and cached[0] is soup:
            return cached[1]

        tag = soup.select_one("script#__NEXT_DATA__")
        if not isinstance(tag, Tag):
            raise LNException("Work page has no __NEXT_DATA__ state")
        try:
            data = json.loads(tag.get_text())
            state = data["props"]["pageProps"]["__APOLLO_STATE__"]
        except (ValueError, KeyError, TypeError):
            raise LNException("Unexpected work page state")
        work_id = re.search(r"/works/(\d+)", self.novel_url)
        if not work_id:
            raise LNException("Unknown work id in novel url")
        work = state.get(f"Work:{work_id.group(1)}")
        if not isinstance(work, dict):
            raise LNException("Work missing from page state")
        self._work_cache = (soup, (state, work))
        return state, work

    def parse_chapter_list(
        self, soup: BeautifulSoup
    ) -> Generator[Union[Volume, Chapter], None, None]:
        state, work = self._work_state(soup)
        work_id = re.search(r"/works/(\d+)", self.novel_url).group(1)
        # tableOfContentsV2 is in reading order: each group is one heading
        # (a volume), except a leading group without heading (no volume).
        chap_id = 0
        vol_id = 0
        seen = set()
        for ref in work.get("tableOfContentsV2") or []:
            group = state.get(ref.get("__ref", ""))
            if not isinstance(group, dict):
                continue
            episodes = [
                state.get(e.get("__ref", "")) for e in group.get("episodeUnions") or []
            ]
            episodes = [e for e in episodes if isinstance(e, dict) and e.get("id")]

            new_episodes = []
            for episode in episodes:
                url = self.absolute_url(f"/works/{work_id}/episodes/{episode['id']}")
                if url in seen:
                    continue
                seen.add(url)
                new_episodes.append((url, episode))
            if not new_episodes:
                continue

            heading = None
            if isinstance(group.get("chapter"), dict):
                heading = state.get(group["chapter"].get("__ref", ""))
            volume = None
            if isinstance(heading, dict):
                vol_id += 1
                volume = Volume(id=vol_id, title=heading.get("title") or "")
                yield volume

            for url, episode in new_episodes:
                chap_id += 1
                yield Chapter(
                    id=chap_id,
                    url=url,
                    title=episode.get("title") or "",
                    volume=volume.id if volume is not None else None,
                )

        total = work.get("publicEpisodeCount")
        if isinstance(total, int) and total != chap_id:
            logger.warning("Chapter list has %d of %d episodes", chap_id, total)

    # -- chapter body -------------------------------------------------- #

    def select_chapter_body(self, soup: BeautifulSoup) -> Tag:
        tag = soup.select_one(".widget-episodeBody")
        assert isinstance(tag, Tag)
        return tag
