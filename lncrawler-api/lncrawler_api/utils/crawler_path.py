"""Location of the lncrawler-crawler package and the file names it writes."""
import sys
from pathlib import Path

from django.conf import settings

CRAWLER_DIR = Path(settings.BASE_DIR).parent / "lncrawler-crawler"

# Written by the crawler into each source folder. The API keeps its own copy;
# tests/test_crawler_constants.py checks it against lncrawl.
META_FILE_NAME = "meta.json"


def ensure_crawler_on_path():
    """Add the crawler directory and its parent to the front of ``sys.path``."""
    for path in (CRAWLER_DIR.parent, CRAWLER_DIR):
        p = str(path)
        if p not in sys.path:
            sys.path.insert(0, p)
