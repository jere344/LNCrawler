"""Exception types. The module is intentionally misspelled `exeptions` to stay
import-compatible with upstream lightnovel-crawler sources.
"""

from urllib.error import HTTPError, URLError


class LNException(Exception):
    """Base exception for all crawler errors."""


class FallbackToBrowser(LNException):
    """Raised by a soup parser when the request backend cannot fetch the page,
    so the crawler should retry using the Playwright browser backend."""


# Kept for source compatibility with upstream imports.
ScraperNotSupported = FallbackToBrowser


try:
    from curl_cffi.requests.errors import RequestsError
except Exception:  # pragma: no cover
    try:
        from curl_cffi.requests.exceptions import RequestException as RequestsError
    except Exception:
        RequestsError = URLError

try:
    from PIL import UnidentifiedImageError
except Exception:  # pragma: no cover
    UnidentifiedImageError = OSError


# Errors that should trigger a browser fallback in browser templates.
ScraperErrorGroup = (
    LNException,
    HTTPError,
    URLError,
    RequestsError,
    UnidentifiedImageError,
    OSError,
)

# Errors that are worth retrying at the request level (no browser fallback).
RetryErrorGroup = (HTTPError, URLError, RequestsError, UnidentifiedImageError)
