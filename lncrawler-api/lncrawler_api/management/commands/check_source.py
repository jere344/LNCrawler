"""Smoke-test and inspect a single crawler source.

Consolidates the former ``tools/check_source.py`` and ``tools/inspect_source.py``
into one management command so it can be run through Django (and reused by the
admin "Test source" action).

Smoke test (loads one source, reads novel info, downloads one chapter body):

  python manage.py check_source --url NOVEL_URL [--chapter 1]
  python manage.py check_source --file sources/en/x/foo.py --query "reincarnation"
  python manage.py check_source --file sources/en/x/foo.py --url NOVEL_URL

Exit code 0 = PASS, 1 = FAIL, 2 = framework error.

Inspect (dumps novel page HTML + parsed metadata as JSON):

  python manage.py check_source --inspect --file sources/en/x/foo.py \
      --name FooCrawler --url https://example.com/book/xxx [--html out.html]
"""

import importlib.util
import json
import os
import sys
import tempfile
import threading
import traceback

from django.core.management.base import BaseCommand


def _ensure_crawler_importable():
    from ...services.downloader_service import _load_app

    _load_app()


def _load_class_from_file(path, name=None):
    from lncrawl.core.crawler import Crawler

    module_name = "check_source_" + os.path.basename(path).replace(".py", "")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    classes = [
        v
        for v in vars(module).values()
        if isinstance(v, type)
        and issubclass(v, Crawler)
        and v is not Crawler
        and v.__module__ == module.__name__
        and (name is None or v.__name__ == name)
    ]
    if not classes:
        raise RuntimeError(f"No Crawler subclass found in {path}")
    return classes[0]


def _build_crawler(args):
    from lncrawl.core.sources import get_crawler_by_url, prepare_crawler

    if args.file:
        cls = _load_class_from_file(args.file, args.name)
        url = args.url
        if not url:
            crawler = cls()
            crawler.initialize()
            results = list(crawler.search_novel(args.query) or [])
            crawler.close()
            if not results:
                raise RuntimeError(f"search_novel({args.query!r}) returned nothing")
            first = results[0]
            url = first.get("url") if isinstance(first, dict) else getattr(first, "url", None)
            if not url:
                raise RuntimeError("search result has no url")
        crawler = cls()
        crawler.novel_url = url
        from urllib.parse import urlparse

        crawler.home_url = "{0.scheme}://{0.hostname}/".format(urlparse(url))
        crawler.initialize()
        return cls, crawler

    cls = get_crawler_by_url(args.url)
    if cls is None:
        raise RuntimeError(f"no registered crawler for {args.url}")
    return cls, prepare_crawler(args.url)


def _run_smoke(args):
    from lncrawl.core.novel_info import format_novel

    cls, crawler = _build_crawler(args)
    print("SOURCE:", cls.__name__)
    print("NOVEL_URL:", crawler.novel_url)
    try:
        crawler.read_novel_info()
        format_novel(crawler)
        print(
            "TITLE: {} | AUTHORS: {} | CHAPTERS: {}".format(
                crawler.novel_title,
                crawler.novel_author,
                len(crawler.chapters),
            )
        )
        if not crawler.novel_title:
            print("RESULT: FAIL empty title")
            return 1
        if not crawler.chapters:
            print("RESULT: FAIL no chapters")
            return 1
        print("SYNOPSIS_LEN:", len(crawler.novel_synopsis or ""))
        nu = getattr(crawler, "novelupdates_url", None)
        if nu:
            print("NOVELUPDATES:", nu)
        idx = max(0, min(args.chapter - 1, len(crawler.chapters) - 1))
        chapter = crawler.chapters[idx]
        body = crawler.download_chapter_body(chapter)
        print("BODY_LEN:", len(body or ""))
        if not body or len(body) < 200:
            print("RESULT: FAIL empty/short chapter body")
            return 1
        print("RESULT: PASS")
        return 0
    finally:
        try:
            crawler.close()
        except Exception:
            pass


def _run_inspect(args):
    cls, crawler = _build_crawler(args)
    result = {
        "source_name": getattr(cls, "source_name", None),
        "source_class": cls.__name__,
        "url": crawler.novel_url,
        "html": "",
        "parsed": {},
        "error": None,
    }
    try:
        html_path = args.html or os.path.join(
            tempfile.gettempdir(), f"{cls.__name__}.html"
        )
        os.makedirs(os.path.dirname(html_path), exist_ok=True)
        try:
            if hasattr(crawler, "get_novel_soup"):
                soup = crawler.get_novel_soup()
            else:
                soup = crawler.get_soup(crawler.novel_url)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(str(soup))
            result["html"] = html_path
        except Exception as e:
            result["html_error"] = f"{type(e).__name__}: {e}"
        try:
            crawler.read_novel_info()
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"
        result["parsed"] = {
            "title": crawler.novel_title,
            "author": crawler.novel_author,
            "cover": crawler.novel_cover,
            "synopsis_len": len(crawler.novel_synopsis or ""),
            "tags": crawler.novel_tags,
            "genres": getattr(crawler, "genres", None),
            "alt_titles": getattr(crawler, "alternative_titles", None),
        }
    finally:
        try:
            crawler.close()
        except Exception:
            pass

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


class Command(BaseCommand):
    help = "Smoke-test (or --inspect) a single crawler source."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--url")
        parser.add_argument("--file")
        parser.add_argument("--name")
        parser.add_argument("--query", default="reincarnation")
        parser.add_argument("--chapter", type=int, default=1)
        parser.add_argument("--timeout", type=int, default=90)
        parser.add_argument("--inspect", action="store_true")
        parser.add_argument("--html", default="")

    def handle(self, *args, **options):
        args = argparse_namespace(options)
        if not args.file and not args.url:
            self.stderr.write("provide --file and/or --url")
            sys.exit(2)

        _ensure_crawler_importable()

        def watchdog():
            print(f"RESULT: FAIL timeout after {args.timeout}s")
            os._exit(1)

        timer = threading.Timer(args.timeout, watchdog)
        timer.daemon = True
        timer.start()
        try:
            code = _run_inspect(args) if args.inspect else _run_smoke(args)
        except Exception as e:
            print("RESULT: FAIL", type(e).__name__, str(e)[:300])
            traceback.print_exc()
            code = 2
        finally:
            timer.cancel()
        sys.exit(code)


def argparse_namespace(options):
    class _Args:
        pass

    args = _Args()
    for key in ("url", "file", "name", "query", "chapter", "timeout", "inspect", "html"):
        setattr(args, key, options.get(key))
    return args
