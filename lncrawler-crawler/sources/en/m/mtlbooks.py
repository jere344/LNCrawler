# -*- coding: utf-8 -*-
"""MTLBooks (mtlbooks.com) - machine-translated novels (Nuxt site, /api/v* endpoints, "MTL" branding). Disabled: Machine-translated (MTL) content — extremely low quality, intentionally excluded."""

from lncrawl.core.crawler import Crawler


class MTLBooksCrawler(Crawler):
    base_url = [
        "https://mtlbooks.com/",
    ]
    language = "en"
    has_mtl = True

    is_disabled = True
    disable_reason = (
        "Machine-translated (MTL) content — extremely low quality, intentionally excluded"
    )
