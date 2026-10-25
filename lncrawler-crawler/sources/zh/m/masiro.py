# -*- coding: utf-8 -*-
"""Masiro (masiro.me). Adult site, disabled: Cloudflare challenge, then login required, see disable_reason."""

from lncrawl.core.crawler import Crawler


class MasiroCrawler(Crawler):
    base_url = "https://masiro.me/"
    language = "zh"
    is_adult = True

    is_disabled = True
    disable_reason = (
        "Cloudflare managed challenge on every request (cf-mitigated: challenge) and login required for bodies "
        "(/admin/auth/login); tested with curl, curl_cffi chrome and safari impersonation, and the real browser "
        "pane where the challenge page stayed on 'Performing security verification'"
    )
