# -*- coding: utf-8 -*-
"""novels.pl — Polish novel site.

Every request returns the Anubis proof-of-work page ("Making sure you're not a
bot!"). That is bot protection, and it must not be bypassed. Disabled.
"""

from lncrawl.core.crawler import Crawler


class NovelsPlCrawler(Crawler):
    base_url = "https://novels.pl/"
    language = "pl"
    has_mtl = False

    is_disabled = True
    disable_reason = "Anubis proof-of-work bot challenge on every request"
