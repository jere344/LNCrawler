import base64
import logging
import os
import random
from io import BytesIO
from typing import Any, Callable, Dict, MutableMapping, Optional, Tuple, Union
from urllib.parse import ParseResult, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi
from PIL import Image, UnidentifiedImageError
from tenacity import (retry, retry_if_exception, stop_after_attempt,
                      wait_random_exponential)

from ..assets.user_agents import user_agents
from ..constants import TIMEOUT
from .exeptions import FallbackToBrowser, LNException
from .soup import SoupMaker
from .taskman import TaskManager

logger = logging.getLogger(__name__)

try:  # curl_cffi versions differ in where RequestsError lives
    from curl_cffi.requests.errors import RequestsError as _CurlError
except Exception:  # pragma: no cover
    try:
        from curl_cffi.requests.exceptions import RequestException as _CurlError
    except Exception:
        _CurlError = Exception  # type: ignore[assignment,misc]

# curl_cffi sentence about the browser TLS fingerprint to impersonate.
DEFAULT_IMPERSONATE = os.getenv("LNCRAWL_IMPERSONATE", "chrome")


def merge_headers(
    base: Optional[MutableMapping], extra: Optional[MutableMapping]
) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(extra or {})
    lowered = {k.lower() for k in out}
    for key, value in (base or {}).items():
        if key.lower() not in lowered:
            out[key] = value
    return out


class Scraper(TaskManager, SoupMaker):
    """Native request backend built on curl_cffi (TLS impersonation)."""

    def __init__(
        self,
        origin: str,
        workers: Optional[int] = None,
        parser: Optional[str] = None,
    ) -> None:
        self.home_url = origin
        self.last_soup_url = ""
        self.last_soup = None
        self.use_proxy = os.getenv("use_proxy")
        # Per-instance default; search tightens this (see core/search.py).
        self.request_timeout = TIMEOUT

        SoupMaker.__init__(self, parser)
        self.init_scraper()
        self.change_user_agent()
        TaskManager.__init__(self, workers)

    # ------------------------------------------------------------------ #
    # Initializers
    # ------------------------------------------------------------------ #

    def init_scraper(self) -> None:
        # Many novel sites serve incomplete certificate chains; upstream also
        # disabled verification (ssl.CERT_NONE). Set LNCRAWL_VERIFY=1 to re-enable.
        verify = os.getenv("LNCRAWL_VERIFY", "").lower() in ("1", "true", "yes")
        for kwargs in (
            {"impersonate": DEFAULT_IMPERSONATE, "verify": verify},
            {"verify": verify},
            {},
        ):
            try:
                self.scraper = cffi.Session(**kwargs)
                return
            except Exception:
                continue
        logger.exception("Failed to initialize curl_cffi session")
        self.scraper = cffi.Session()

    def change_user_agent(self) -> None:
        self.user_agent = random.choice(user_agents)
        try:
            self.scraper.headers["User-Agent"] = self.user_agent
        except Exception:
            pass

    def close(self) -> None:
        """Release the thread pool and the underlying curl session.

        Called when a crawler is done so a long-lived process does not
        accumulate libcurl handles/sockets across searches and downloads.
        """
        self.shutdown()
        scraper = getattr(self, "scraper", None)
        if scraper is not None:
            try:
                scraper.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    def __get_proxies(self, scheme: str) -> Dict[str, str]:
        if self.use_proxy and scheme:
            return {scheme: self.use_proxy}
        return {}

    def __process_request(
        self,
        method: str,
        url: str,
        *args,
        max_retries: Optional[int] = None,
        headers: Optional[MutableMapping] = None,
        **kwargs,
    ):
        method_call: Callable = getattr(self.scraper, method)
        parsed = urlparse(url)

        kwargs = kwargs or {}
        kwargs.setdefault("allow_redirects", True)
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self.request_timeout
        proxies = self.__get_proxies(parsed.scheme)
        if proxies:
            kwargs["proxies"] = proxies

        default_headers = {
            "Origin": self.home_url.strip("/"),
            "Referer": self.last_soup_url or self.home_url,
            "User-Agent": self.user_agent,
        }
        request_headers = merge_headers(default_headers, headers)

        def _is_retryable(exc: BaseException) -> bool:
            # Retry transport errors and 5xx/429, but never a plain 4xx:
            # retrying a 404/403 wastes the whole backoff budget per dead URL.
            if not isinstance(exc, _CurlError):
                return False
            status = getattr(getattr(exc, "response", None), "status_code", None)
            return status is None or status == 429 or status >= 500

        @retry(
            stop=stop_after_attempt(
                (self.workers + 3) if max_retries is None else max_retries + 1
            ),
            wait=wait_random_exponential(multiplier=0.5, max=60),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )
        def _do_request():
            with self.domain_gate(parsed.hostname):
                response = method_call(url, *args, **kwargs, headers=request_headers)
                response.raise_for_status()
                response.encoding = "utf8"
            return response

        return _do_request()

    # ------------------------------------------------------------------ #
    # Properties / helpers
    # ------------------------------------------------------------------ #

    @property
    def origin(self) -> ParseResult:
        return urlparse(self.home_url)

    @property
    def headers(self) -> Dict[str, Any]:
        try:
            return dict(self.scraper.headers)
        except Exception:
            return {}

    def set_header(self, key: str, value: str) -> None:
        self.scraper.headers[key] = value

    @property
    def cookies(self) -> Dict[str, Optional[str]]:
        cookies = self.scraper.cookies
        if hasattr(cookies, "get_dict"):
            try:
                return dict(cookies.get_dict())
            except Exception:
                pass
        try:
            return {k: v for k, v in cookies.items()}
        except Exception:
            return {}

    def set_cookie(self, name: str, value: str) -> None:
        self.scraper.cookies.set(name, value)

    def absolute_url(self, url: str, page_url: Optional[str] = None) -> str:
        from urllib.parse import urljoin

        url = str(url or "").strip()
        if not url:
            return url
        if url.startswith("data:") or len(url) >= 1024:
            return url
        if not page_url:
            page_url = str(self.last_soup_url or self.home_url)
        return urljoin(page_url, url).rstrip("/")

    # ------------------------------------------------------------------ #
    # Request helpers
    # ------------------------------------------------------------------ #

    def get_response(
        self,
        url: str,
        timeout: Optional[Union[float, Tuple[float, float]]] = None,
        **kwargs,
    ):
        return self.__process_request("get", url, timeout=timeout, **kwargs)

    def post_response(
        self,
        url: str,
        data: Optional[MutableMapping] = None,
        max_retries: Optional[int] = 0,
        **kwargs,
    ):
        return self.__process_request(
            "post", url, data=data, max_retries=max_retries, **kwargs
        )

    def submit_form(
        self,
        url: str,
        data: Optional[MutableMapping] = None,
        multipart: bool = False,
        headers: Optional[MutableMapping] = None,
        **kwargs,
    ):
        headers = merge_headers(
            {
                "Content-Type": (
                    "multipart/form-data"
                    if multipart
                    else "application/x-www-form-urlencoded; charset=UTF-8"
                )
            },
            headers,
        )
        return self.post_response(url, data=data, headers=headers, **kwargs)

    def download_file(self, url: str, output_file: str, **kwargs) -> None:
        response = self.__process_request("get", url, **kwargs)
        with open(output_file, "wb") as f:
            f.write(response.content)

    def download_image(self, url: str, headers: Optional[MutableMapping] = None, **kwargs):
        if url.startswith("data:"):
            content = base64.b64decode(url.split("base64,")[-1])
            return Image.open(BytesIO(content))

        headers = merge_headers({"Origin": None, "Referer": None}, headers)
        try:
            response = self.__process_request("get", url, headers=headers, **kwargs)
            return Image.open(BytesIO(response.content))
        except UnidentifiedImageError:
            headers = merge_headers(
                {"Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.9"},
                headers,
            )
            response = self.__process_request("get", url, headers=headers, **kwargs)
            return Image.open(BytesIO(response.content))

    def get_json(self, url: str, headers: Optional[MutableMapping] = None, **kwargs) -> Any:
        headers = merge_headers({"Accept": "application/json,text/plain,*/*"}, headers)
        return self.get_response(url, headers=headers, **kwargs).json()

    def post_json(
        self,
        url: str,
        data: Optional[MutableMapping] = None,
        headers: Optional[MutableMapping] = None,
        **kwargs,
    ) -> Any:
        headers = merge_headers(
            {"Content-Type": "application/json", "Accept": "application/json,text/plain,*/*"},
            headers,
        )
        return self.post_response(url, data=data, headers=headers, **kwargs).json()

    def submit_form_json(
        self,
        url: str,
        data: Optional[MutableMapping] = None,
        headers: Optional[MutableMapping] = None,
        multipart: bool = False,
        **kwargs,
    ) -> Any:
        headers = merge_headers({"Accept": "application/json,text/plain,*/*"}, headers)
        return self.submit_form(
            url, data=data, headers=headers, multipart=bool(multipart), **kwargs
        ).json()

    def get_soup(
        self,
        url: str,
        headers: Optional[MutableMapping] = None,
        encoding: Optional[str] = None,
        **kwargs,
    ) -> BeautifulSoup:
        headers = merge_headers(
            {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9"}, headers
        )
        response = self.get_response(url, headers=headers, **kwargs)
        self.last_soup_url = url
        soup = self.make_soup(response, encoding)
        self.last_soup = soup
        return soup

    def post_soup(
        self,
        url: str,
        data: Optional[MutableMapping] = None,
        headers: Optional[MutableMapping] = None,
        encoding: Optional[str] = None,
        **kwargs,
    ) -> BeautifulSoup:
        headers = merge_headers(
            {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9"}, headers
        )
        response = self.post_response(url, data=data, headers=headers, **kwargs)
        return self.make_soup(response, encoding)

    def submit_form_for_soup(
        self,
        url: str,
        data: Optional[MutableMapping] = None,
        headers: Optional[MutableMapping] = None,
        multipart: bool = False,
        encoding: Optional[str] = None,
        **kwargs,
    ) -> BeautifulSoup:
        headers = merge_headers(
            {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9"}, headers
        )
        response = self.submit_form(
            url, data=data, headers=headers, multipart=bool(multipart), **kwargs
        )
        return self.make_soup(response, encoding)


__all__ = ["Scraper", "FallbackToBrowser", "LNException"]
