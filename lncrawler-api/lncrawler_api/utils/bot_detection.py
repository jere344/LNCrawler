import re

# Catches generic/unknown bots and headless browsers that nginx's named list
# (which decides who gets SEO pages) deliberately leaves out. Also the fallback
# when a request did not come through nginx (tests, internal calls). "bot" only
# as a whole word or before a version/separator, and never in the "Cubot" phone
# brand, which shows up as "CUBOT;" or "CUBOT/X19" in real browser UAs.
_GENERIC_BOT_UA = re.compile(
    r"(?<!cu)bot[/;]|\bbot\b|crawl|spider|slurp|headlesschrome|lighthouse|mediapartners-google",
    re.IGNORECASE,
)


def is_bot_request(request):
    """
    True when nginx flagged the request as a known crawler, or its User-Agent looks like a bot
    """
    if request.META.get("HTTP_X_RENDER_SEO") == "1":
        return True
    return bool(_GENERIC_BOT_UA.search(request.META.get("HTTP_USER_AGENT", "")))
