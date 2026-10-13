# -*- coding: utf-8 -*-
"""Estar / Ebristar (エブリスタ). Disabled; see disable_reason."""

from lncrawl.core.crawler import Crawler


class EstarCrawler(Crawler):
    base_url = "https://estar.jp/"
    language = "ja"
    has_mtl = False

    is_disabled = True
    disable_reason = 'No reliable listing: ranking/trend/finished pages carry no work ids in server-rendered HTML (only /page/promotion/popular_works exposes a few). Body text is in a devalue-encoded Nuxt payload with ruby markup and needs custom decoding.'
