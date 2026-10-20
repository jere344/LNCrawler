"""Sanitizing of untrusted text and HTML for the server-rendered SEO pages."""

from lxml_html_clean import Cleaner

from .text import strip_html


# Chapter bodies come from arbitrary third-party sites. Most crawler adapters
# clean them at ingestion, but some (e.g. wattpad) return raw remote HTML, so we
# cannot trust stored bodies when serving them as HTML on our own origin. This
# mirrors the allowlist DOMPurify applies in the SPA reader.
_BODY_CLEANER = Cleaner(
    allow_tags={
        "p", "br", "div", "span", "em", "strong", "b", "i", "u", "s", "a", "img",
        "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote", "pre",
        "code", "table", "thead", "tbody", "tr", "td", "th", "figure", "figcaption",
        "hr", "sub", "sup", "small", "mark",
    },
    safe_attrs_only=True,
    safe_attrs={"href", "src", "alt", "title", "width", "height", "colspan", "rowspan"},
    javascript=True,
    style=True,
    scripts=True,
    embedded=True,
    frames=True,
    forms=True,
    meta=True,
    links=True,
    page_structure=True,
    processing_instructions=True,
    comments=True,
)


def _clean_text(value, limit=300):
    text = " ".join(strip_html(value).split())
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _sanitize_body(body, images_path):
    # Bodies store relative `images/<file>`; the SPA rewrites these too. Then
    # clean the untrusted HTML before it is rendered with |safe.
    body = body or ""
    if images_path:
        body = body.replace('src="images/', f'src="{images_path}/')
    return _BODY_CLEANER.clean_html(body)
