# -*- coding: utf-8 -*-
"""Lorenovels (lorenovels.com). Disabled: membership login gate after a free preview."""

from lncrawl.core.crawler import Crawler


class LorenovelsCrawler(Crawler):
    base_url = [
        "https://lorenovels.com/",
    ]
    language = "en"
    login_required = True

    is_disabled = True
    disable_reason = (
        "Chapters after the free preview, about 65 of 81 on the tested novel, "
        "require a logged-in Premium membership; anonymous fetch returns a login prompt"
    )
