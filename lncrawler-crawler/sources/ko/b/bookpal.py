# -*- coding: utf-8 -*-
"""Bookpal (bookpal.co.kr, Korean web novels). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class BookpalCrawler(Crawler):
    base_url = "https://www.bookpal.co.kr/"
    language = "ko"
    has_mtl = False

    is_disabled = True
    disable_reason = (
        "Platform shutdown: the public home API (POST https://api7.bookpal.co.kr/api/"
        "genre/novel_home) returns a banner titled '북팔 플랫폼 서비스 종료 안내' (Bookpal "
        "platform service termination notice), with an image dated 2026-07. "
        "book/chapter_list for a tested book id returns code 204 'stop_book'. "
        "The SPA is a client-side shell, and the JSON API is POST-only (GET returns 405). "
        "Bookpal's ranking_list and freeview endpoints returned empty or 400 'empty_no' "
        "for the bodies tried, so no free-chapter text was confirmed."
    )
