"""Slug generation shared across the API.

The library folder name is the novel's identity, so the API must slugify text
with the same algorithm the crawler uses to name those folders. Django's
``slugify`` strips anything non-ASCII, collapsing a Korean or Russian title to an
empty string or a stray Latin letter -- ``"s급 헌터"`` becomes ``"s"``. The
crawler uses python-slugify (with text-unidecode) which transliterates instead,
so the API re-exports it here as the single slugify for slug derivation.
"""
from slugify import slugify

__all__ = ["slugify"]
