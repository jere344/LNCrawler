"""Constants and pure helpers shared by the prune phases."""

import logging
from datetime import timedelta

from lncrawler_api.utils.chapter_utils import FAIL_MESSAGE
from lncrawler_api.utils.lncrawler_paths import sanitize
from lncrawler_api.utils.text import strip_html

logger = logging.getLogger("lncrawler_api")

# A novel is never pruned before it has had time to settle, so a fresh crawl
# (or a bad first import) cannot be wiped before it is even reviewed.
MIN_NOVEL_AGE = timedelta(days=7)

# Phase 3 compares at most this many words per chapter. Translations of the same
# chapter share their prose either way, and the cap bounds SequenceMatcher's
# worst case on very long chapters.
MAX_COMPARE_WORDS = 4000

# Phase 3 verdicts ("kept, nothing changed") persisted between runs.
VERDICTS_FILE = "prune_phase3_kept.json"

# A sample shorter than this is a placeholder (a failed download leaves a short
# stub body), not content, so it is ignored instead of counted as a mismatch.
MIN_SAMPLE_WORDS = 50


def normalize_source_name(name: str) -> str:
    """Same normalization for registry names and DB source names."""
    if not name:
        return ""
    normalized = sanitize(str(name)).lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def normalize_body(body) -> str:
    if not body:
        return ""
    text = strip_html(str(body)).replace(FAIL_MESSAGE, "")
    return " ".join(text.split()).lower()


def tokenize_body(text) -> list:
    """Word tokens of a normalized body, capped at ``MAX_COMPARE_WORDS``."""
    return (text or "").split()[:MAX_COMPARE_WORDS]


class _UnmappedComments(Exception):
    """Porting a source would lose comments (no --force), so its deletion is refused."""

    def __init__(self, count):
        super().__init__(f"{count} comment(s) cannot be mapped to the keeper")
        self.count = count
