"""Source discovery and registry.

Walks the sibling `sources/` directory, imports every crawler module and
registers its `Crawler` subclasses by hostname. Sources are plain Python files
(the same authoring model as lightnovel-crawler) placed under
`sources/<lang>/...`.
"""

import importlib.util
import logging
import os
import sys
from hashlib import md5
from typing import Dict, List, Optional, Type
from urllib.parse import urlparse

from ..constants import SOURCES_DIR
from .crawler import Crawler

logger = logging.getLogger(__name__)

crawler_list: List[Type[Crawler]] = []
crawler_map: Dict[str, Type[Crawler]] = {}
rejected_sources: List[str] = []
_loaded = False


def _register(cls: Type[Crawler]) -> None:
    base_urls = cls.base_url
    if isinstance(base_urls, str):
        base_urls = [base_urls]
    normalized = []
    for url in base_urls:
        url = str(url).strip().lower().rstrip("/")
        if not url:
            continue
        normalized.append(url)
        crawler_map[url] = cls
        crawler_map[url.replace("https://", "http://")] = cls
        crawler_map[url.replace("http://", "https://")] = cls
        host = urlparse(url).hostname
        if host:
            crawler_map[host] = cls
            if host.startswith("www."):
                crawler_map[host[4:]] = cls
            else:
                crawler_map["www." + host] = cls
    cls.base_url = normalized
    if normalized and not getattr(cls, "source_name", ""):
        cls.source_name = urlparse(normalized[0]).netloc
    crawler_list.append(cls)


def _import_module_from_path(path: str):
    name = "lncrawl_source_" + md5(path.encode()).hexdigest()
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _language_from_path(path: str) -> Optional[str]:
    rel = os.path.relpath(path, SOURCES_DIR)
    parts = rel.split(os.sep)
    if len(parts) >= 2:
        candidate = parts[0]
        if len(candidate) == 2 and candidate.isalpha():
            # `jp` is the upstream directory name; the ISO code is `ja`.
            return {"jp": "ja"}.get(candidate, candidate)
    return None


def load_sources(force: bool = False) -> List[Type[Crawler]]:
    global _loaded
    if _loaded and not force:
        return crawler_list

    crawler_list.clear()
    crawler_map.clear()

    for root, _dirs, files in os.walk(SOURCES_DIR):
        if "__pycache__" in root:
            continue
        for file in files:
            if not file.endswith(".py") or file.startswith("_"):
                continue
            path = os.path.join(root, file)
            try:
                module = _import_module_from_path(path)
            except Exception as e:
                logger.warning("Failed to import source %s: %s", file, e)
                continue
            if module is None:
                continue

            language = _language_from_path(path)
            for value in vars(module).values():
                if (
                    isinstance(value, type)
                    and issubclass(value, Crawler)
                    and value is not Crawler
                    and value.__module__ == module.__name__
                ):
                    if language and not value.language:
                        value.language = language
                    value.file_path = path  # type: ignore[attr-defined]
                    _register(value)

    _loaded = True
    logger.info("Loaded %d source(s)", len(crawler_list))
    return crawler_list


def get_search_crawlers() -> List[Type[Crawler]]:
    load_sources()
    return [
        cls
        for cls in crawler_list
        if cls.search_novel is not Crawler.search_novel
        and not cls.is_disabled
        and not cls.disable_reason
    ]


def get_browse_crawlers() -> List[Type[Crawler]]:
    """Sources that can list novels from a browse/all-novels/ranking section."""
    load_sources()
    return [
        cls
        for cls in crawler_list
        if cls.browse_novels is not Crawler.browse_novels
        and not cls.is_disabled
        and not cls.disable_reason
    ]


def get_crawler_by_url(url: str) -> Optional[Type[Crawler]]:
    load_sources()
    host = urlparse(url).hostname
    if not host:
        return None
    if host in crawler_map:
        return crawler_map[host]
    # Fall back to a hostname match that allows subdomains. Never compare the
    # raw URL prefix: `https://site.com@169.254.169.254/` starts with the
    # registered base_url but resolves to a different host (SSRF).
    host = host.lower().lstrip(".")
    for registered, cls in crawler_map.items():
        if "://" in registered:
            continue
        registered = registered.lower().lstrip(".")
        if host == registered or host.endswith("." + registered):
            return cls
    return None


def prepare_crawler(url: str, crawler_file: Optional[str] = None) -> Crawler:
    """Instantiate the right crawler for the given novel URL."""
    load_sources()

    if crawler_file:
        module = _import_module_from_path(crawler_file)
        if module is None:
            raise ValueError(f"Could not load crawler file: {crawler_file}")
        classes = [
            v
            for v in vars(module).values()
            if isinstance(v, type)
            and issubclass(v, Crawler)
            and v is not Crawler
            and v.__module__ == module.__name__
        ]
        if not classes:
            raise ValueError(f"No crawler found in {crawler_file}")
        crawler_type = classes[0]
    else:
        crawler_type = get_crawler_by_url(url)
        if crawler_type is None:
            host = urlparse(url).hostname
            raise ValueError(f"No crawler available for host: {host}")

    crawler = crawler_type()
    crawler.novel_url = url
    crawler.home_url = "{0.scheme}://{0.hostname}/".format(urlparse(url))
    crawler.initialize()

    if getattr(crawler, "login_required", False):
        username, password = crawler.get_credentials()
        if username:
            crawler.login(username, password)

    return crawler
