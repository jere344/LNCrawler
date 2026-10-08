"""Source discovery and registry.

Walks the sibling `sources/` directory, imports every crawler module and
registers its `Crawler` subclasses by hostname. Sources are plain Python files
(the same authoring model as lightnovel-crawler) placed under
`sources/<lang>/...`.
"""

import ast
import importlib.util
import logging
import os
import sys
from hashlib import md5
from typing import Dict, Iterable, List, Optional, Type
from urllib.parse import urlparse

from ..constants import SOURCES_DIR
from .crawler import Crawler

logger = logging.getLogger(__name__)

crawler_list: List[Type[Crawler]] = []
crawler_map: Dict[str, Type[Crawler]] = {}
rejected_sources: List[str] = []
_loaded = False

# Lazy source index: host -> source file. Built from a static AST scan of the
# source files so a download imports only the one file it needs instead of the
# whole `sources/` tree (~170 files, tens of MB of modules).
_index_hosts: Dict[str, str] = {}
_index_built = False
_loaded_files: set = set()


def _register_keys(url: str) -> Iterable[str]:
    """Every host/lookup key `_register` maps for one normalized base URL."""
    yield url
    yield url.replace("https://", "http://")
    yield url.replace("http://", "https://")
    host = urlparse(url).hostname
    if host:
        yield host
        if host.startswith("www."):
            yield host[4:]
        else:
            yield "www." + host


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
        for key in _register_keys(url):
            crawler_map[key] = cls
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


def _apply_module(path: str, module) -> List[Type[Crawler]]:
    """Set language/file_path and register every Crawler subclass in a module.

    Shared by full discovery and lazy single-file loading so both produce
    identical registry state (host aliases and auto ``source_name``).
    """
    language = _language_from_path(path)
    found = []
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
            found.append(value)
    return found


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
            _apply_module(path, module)

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


def _iter_source_files():
    for root, _dirs, files in os.walk(SOURCES_DIR):
        if "__pycache__" in root:
            continue
        for file in files:
            if file.endswith(".py") and not file.startswith("_"):
                yield os.path.join(root, file)


def _literal_strings(node) -> List[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple)):
        out: List[str] = []
        for element in node.elts:
            out.extend(_literal_strings(element))
        return out
    return []


def _literals_from_file(path: str) -> List[str]:
    """Return the literal ``base_url`` values declared in a source file.

    Every shipped source declares ``base_url`` as a literal, so a static scan
    is enough to pick the file for a host without importing anything.
    """
    try:
        with open(path, "r", encoding="utf-8") as fp:
            tree = ast.parse(fp.read(), path)
    except (OSError, SyntaxError):
        return []
    values: List[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if not any(
                isinstance(t, ast.Name) and t.id == "base_url" for t in stmt.targets
            ):
                continue
            values.extend(_literal_strings(stmt.value))
    return values


def _ensure_index() -> None:
    global _index_built
    if _index_built:
        return
    for path in _iter_source_files():
        for base in _literals_from_file(path):
            base = base.strip().lower().rstrip("/")
            if not base:
                continue
            if "://" not in base:
                base = "http://" + base
            for key in _host_keys(base):
                _index_hosts.setdefault(key, path)
    _index_built = True
    logger.debug("Indexed %d source host(s)", len(_index_hosts))


def _host_keys(url: str) -> Iterable[str]:
    host = urlparse(url).hostname
    if not host:
        return
    yield host
    if host.startswith("www."):
        yield host[4:]
    else:
        yield "www." + host


def _load_source_file(path: str) -> None:
    if path in _loaded_files:
        return
    _loaded_files.add(path)
    try:
        module = _import_module_from_path(path)
    except Exception as e:
        logger.warning("Failed to import source %s: %s", path, e)
        return
    if module is not None:
        _apply_module(path, module)


def _lookup(host: str) -> Optional[Type[Crawler]]:
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


def get_crawler_by_url(url: str) -> Optional[Type[Crawler]]:
    host = urlparse(url).hostname
    if not host:
        return None

    # Hot download path: import just the one source that owns this host.
    if not _loaded:
        _ensure_index()
        host_key = host.lower().lstrip(".")
        path = _index_hosts.get(host_key)
        if path is None:
            for registered, candidate in _index_hosts.items():
                if host_key == registered or host_key.endswith("." + registered):
                    path = candidate
                    break
        if path is not None:
            _load_source_file(path)
            cls = _lookup(host)
            if cls is not None:
                return cls

    load_sources()
    return _lookup(host)


def prepare_crawler(url: str, crawler_file: Optional[str] = None) -> Crawler:
    """Instantiate the right crawler for the given novel URL."""
    if crawler_file:
        module = _import_module_from_path(crawler_file)
        if module is None:
            raise ValueError(f"Could not load crawler file: {crawler_file}")
        classes = _apply_module(crawler_file, module)
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
