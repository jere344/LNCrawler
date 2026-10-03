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

logger = logging.getLogger("frontend")

_RATE_LIMIT = 30  # requests per IP per window
_RATE_WINDOW = 3600


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


@csrf_exempt
@require_POST
def report_error(request):
    ip = _client_ip(request)
    key = f"report-error:{ip}"
    count = cache.get(key, 0)
    if count >= _RATE_LIMIT:
        return JsonResponse({"detail": "rate limited"}, status=429)
    # LocMemCache is per-worker; good enough to blunt accidental loops.
    cache.set(key, count + 1, _RATE_WINDOW)

    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        payload = {}

    message = str(payload.get("message", "Unknown frontend error"))[:2000]
    stack = str(payload.get("stack", ""))[:5000]
    url = str(payload.get("url", ""))[:500]
    context = str(payload.get("context", ""))[:500]

    logger.error(
        "Frontend error: %s",
        message,
        extra={"github_details": f"url={url}\ncontext={context}\n\n{stack}"},
    )
    return JsonResponse({"detail": "ok"})
