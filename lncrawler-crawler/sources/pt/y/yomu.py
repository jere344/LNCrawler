# -*- coding: utf-8 -*-
"""Yomu (yomu.com.br) — Brazilian Portuguese reader for mangas, manhwas and novels.

Next.js front end. Behind a Cloudflare bot wall: plain curl gets HTTP 403, but
curl_cffi with ``impersonate="chrome"`` loads the home page (HTTP 200). No novel
JSON endpoint was found in the public bundles (only ``/api/stats`` and
``/api/settings/ads``), chapter bodies are not reachable without reverse
engineering the app's server actions, and the site has a ``/premium`` tier.
"""

from lncrawl.core.crawler import Crawler


class YomuCrawler(Crawler):
    base_url = ["https://yomu.com.br/"]
    language = "pt"

    is_disabled = True
    disable_reason = (
        "Cloudflare-fronted Next.js app: curl gets 403, curl_cffi chrome "
        "impersonation gets 200 on the home page, but no novel API is exposed "
        "in the public JS bundles (only /api/stats and /api/settings/ads), and "
        "chapter bodies are not reachable without reversing app internals. "
        "Premium tier present. Revisit if a novel endpoint appears."
    )
