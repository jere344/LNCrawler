from urllib.parse import quote

from django.conf import settings


def build_media_url(path):
    """Absolute, URL-encoded public URL for a stored LNCRAWL media path."""
    if not path:
        return None
    return quote(f"{settings.SITE_API_URL}/{settings.LNCRAWL_URL}{path}", safe=':/')
