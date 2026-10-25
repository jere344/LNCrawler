# -*- coding: utf-8 -*-
"""17k.com - Chinese web novel platform.

Disabled: most chapters are VIP-paywalled. Chapter lists mark VIP chapters
with `span.ellipsis.vip`. Sampled books were 88-97% VIP: popular (归一 88%,
吞天记 97%), completed (第九特区 95%) and the free channel's 大千劫主 (97%).
Only the first ~60-130 chapters are free on those, so a full-novel download
would be partial. One free-channel book (3669451, 130 chapters) was fully free.

Probed via the crawler scraper (curl_cffi chrome impersonation) on
2026-10-25: 13 requests, all 200 with real content. No Aliyun WAF challenge
was seen. The earlier "WAF blocks curl_cffi" note no longer holds, so the
block is now the paywall.
"""

from lncrawl.core.crawler import Crawler


class Crawler17k(Crawler):
    base_url = "https://www.17k.com/"
    language = "zh"
    has_mtl = False

    is_disabled = True
    disable_reason = "Most chapters are VIP-paywalled (88-97% VIP in sampled popular and completed books; free part is only a preview window). Pages load via curl_cffi, no WAF challenge seen."
