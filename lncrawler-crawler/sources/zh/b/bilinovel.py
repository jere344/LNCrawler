# -*- coding: utf-8 -*-
"""哔哩轻小说 (bilinovel.com). Disabled: chapter bodies are truncated server-side, see disable_reason."""

from lncrawl.core.crawler import Crawler


class BilinovelCrawler(Crawler):
    base_url = "https://www.bilinovel.com/"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = (
        "chapter bodies truncated server-side: every page ends with a cut paragraph and "
        "the marker 內容加載失敗！請刷新或更換瀏覽器, and the text between pages is missing "
        "(novel 2 chapter 110531 pages 1-4); reproduced with curl, curl_cffi chrome "
        "impersonation and the built-in browser pane; catalog and metadata are fine, "
        "not a bot wall"
    )
