# -*- coding: utf-8 -*-
"""
8book.com (無限小說), raw traditional Chinese, free.

Stub, not implemented. What was learned so it can be revisited:
- Novel page: /novelbooks/<nid>. Chapter list in #chapters .folder, each chapter
  in a.episode_li. Chapter hrefs point to a wrong host (finance.binaccount.com),
  so rebuild them as https://8book.com/read/<nid>/?<cid>.
- Search: /search/?key=<query>, cards div.col-12.col-md-6.col-lg-4.p-2 with
  a[href^="/novelbooks/"].
- Browse: /booklists/update/<n>.html, 30 cards per page with the same selector.
- Chapter body: /txt/4/<nid>/<cid><tok>.html, with tok taken from an obfuscated
  inline script. The variable names and constants change per novel (the
  q521041 template worked for novel 195466 only, not for 121304).
"""
import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class Book8Crawler(Crawler):
    base_url = ["https://8book.com/", "https://www.8book.com/"]
    language = "zh"

    is_disabled = True
    disable_reason = (
        "Chapter bodies are fetched from URLs built by per-novel obfuscated inline JS "
        "(variable names and constants change per novel); not reproducible without "
        "running site JS"
    )
