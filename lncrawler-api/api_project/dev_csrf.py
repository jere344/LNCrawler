from django.middleware.csrf import CsrfViewMiddleware


class DevCsrfViewMiddleware(CsrfViewMiddleware):
    """DEBUG only: accept any Origin/Referer so the app can be tested from any
    URL. The CSRF token itself is still checked."""

    def _origin_verified(self, request):
        return True

    def _check_referer(self, request):  # pragma: no cover - HTTPS-only path
        return None
