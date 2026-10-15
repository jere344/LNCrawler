# -*- coding: utf-8 -*-
import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class NovelFranceCrawler(Crawler):
    base_url = ["https://novelfrance.fr/"]
    language = "fr"

    is_disabled = True
    disable_reason = (
        "Free French reader (Next.js, JSON at /api/novels and /api/novels/{slug}). "
        "Disabled for now: the API exposes no chapter list, the chapter index is only "
        "partially server-rendered, and about 734 novels are mass-imported with "
        "translatorName null. Chapter 1 credits a human team (WeTried), but MTL "
        "status is unverified, so it stays disabled until reviewed."
    )
