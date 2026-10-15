# -*- coding: utf-8 -*-
"""novel.fc2.com (Japanese amateur web novels). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class NovelFc2Crawler(Crawler):
    base_url = "https://novel.fc2.com/"
    language = "ja"
    has_mtl = False

    is_disabled = True
    disable_reason = (
        "novel.fc2.com answers HTTP 403 with a Cloudflare challenge (server 'cloudflare', "
        "cf-mitigated) to plain curl, so the novel pages cannot be fetched over static "
        "HTTP. The fc2.com root responds normally. Tested with curl only; a real "
        "browser session was not tried, so the decision is provisional."
    )
