"""Endpoint for the browser to report unexpected errors.

The GitHub token never reaches the browser: the frontend POSTs here and the
backend raises the issue through the shared logging handler. Client (4xx)
errors are filtered out in the frontend, so only unexpected errors arrive.
"""

import json
import logging

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from api_project.github_issues import fingerprint
from api_project.redaction import redact
from lncrawler_api.utils import get_client_ip

logger = logging.getLogger("frontend")

_RATE_LIMIT = 30  # requests per IP per window
_RATE_WINDOW = 3600


@csrf_exempt
@require_POST
def report_error(request):
    ip = get_client_ip(request)
    key = f"report-error:{ip}"
    # add() starts the window atomically (only the first request sets it),
    # incr() then counts without re-arming the TTL. LocMemCache is per-worker;
    # good enough to blunt accidental loops.
    if not cache.add(key, 1, _RATE_WINDOW):
        try:
            count = cache.incr(key)
        except ValueError:
            # Window expired between add and incr: start a fresh one.
            cache.add(key, 1, _RATE_WINDOW)
            count = 1
        if count > _RATE_LIMIT:
            return JsonResponse({"detail": "rate limited"}, status=429)

    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        payload = {}

    message = str(payload.get("message", "Unknown frontend error"))[:2000]
    stack = str(payload.get("stack", ""))[:5000]
    # Drop the query string: it can carry tokens/emails/IDs into the tracker.
    url = str(payload.get("url", "")).split("?")[0][:500]
    context = str(payload.get("context", ""))[:500]

    logger.error(
        "Frontend error: %s",
        redact(message),
        extra={
            # Fold the endpoint into the fingerprint: the message alone
            # ("Request failed with status code 500") is identical for every
            # failing route, so without this all of them dedup into one report.
            "github_fingerprint": fingerprint(
                "frontend", redact(message), context, url
            ),
            "github_details": redact(f"url={url}\ncontext={context}\n\n{stack}"),
        },
    )
    return JsonResponse({"detail": "ok"})
