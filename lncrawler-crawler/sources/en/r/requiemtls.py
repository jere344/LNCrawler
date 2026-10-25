# -*- coding: utf-8 -*-
"""Requiem MTL (requiemtls.com) - "Requiem MTL" edited machine translations; bot-check interstitial. Disabled: Machine-translated (MTL) content — extremely low quality, intentionally excluded."""

from lncrawl.core.crawler import Crawler


class RequiemMTLCrawler(Crawler):
    base_url = [
        "https://requiemtls.com/",
    ]
    language = "en"
    has_mtl = True

    is_disabled = True
    disable_reason = (
        "Machine-translated (MTL) content — extremely low quality, intentionally excluded"
    )
