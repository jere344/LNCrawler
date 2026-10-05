import os

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


DEFAULT_WORKERS = _env_int("LNCRAWL_WORKERS", 5) or 5
MAX_REQUESTS_PER_DOMAIN = _env_int("LNCRAWL_MAX_PER_DOMAIN", 5) or 5
DEFAULT_PARSER = "lxml"
META_FILE_NAME = "meta.json"
DEFAULT_OUTPUT_PATH = os.getenv("LNCRAWL_OUTPUT_PATH") or os.path.abspath("Lightnovels")
TIMEOUT = (
    _env_int("LNCRAWL_CONNECT_TIMEOUT", 7) or 7,
    _env_int("LNCRAWL_READ_TIMEOUT", 301) or 301,
)

# Directory that contains this package, and the sibling `sources/` folder.
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(PACKAGE_DIR)
SOURCES_DIR = os.path.join(ROOT_DIR, "sources")
