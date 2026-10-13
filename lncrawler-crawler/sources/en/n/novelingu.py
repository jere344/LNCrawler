# -*- coding: utf-8 -*-
"""Novelingua (novelingua.com) — KR/CN/JP novels, provenance unverified.

Verified 2026-10: the site is reachable (Cloudflare-proxied, no challenge) and
chapter routes are server-rendered at ``/blog/<slug>-chapter-N/`` with the prose
in ``.entry-content``, so it would be trivially crawlable.

It is disabled because the translations look like edited MTL and no human
translation could be confirmed:

* The site is operated by "AL_Squad" (Copyright © AL_Squad) and its own Patreon
  page advertises 17-18 chapters/day across 20+ series — far beyond human
  throughput — with no named translators anywhere.
* The prose carries machine-translation artifacts ("Trash that wouldn't be
  satisfying even if killed several times", literal idiom renderings).

Per project policy (unverified/MTL provenance) it is disabled rather than
shipped as a working source.
"""

import logging

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)


class NovelinguCrawler(Crawler):
    base_url = "https://novelingua.com/"
    language = "en"
    has_mtl = True

    is_disabled = True
    disable_reason = (
        "MTL/unverified provenance: operated by AL_Squad at 17-18 chapters/day "
        "across 20+ series with no named human translators and visible "
        "edited-MTL artifacts; human translation could not be confirmed."
    )
