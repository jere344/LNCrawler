"""Core machinery for lncrawler-crawler."""

import logging

from ..constants import PACKAGE_DIR, ROOT_DIR, SOURCES_DIR
from .crawler import Crawler
from .exeptions import *  # noqa: F401,F403
from .novel_info import format_novel, save_metadata

logger = logging.getLogger(__name__)


def init() -> None:
    """Idempotent process-wide setup. Kept for API/bot compatibility."""
    if getattr(init, "_done", False):
        return
    init._done = True  # type: ignore[attr-defined]
    logging.getLogger("lncrawl").addHandler(logging.NullHandler())


__all__ = [
    "Crawler",
    "init",
    "format_novel",
    "save_metadata",
    "PACKAGE_DIR",
    "ROOT_DIR",
    "SOURCES_DIR",
]
