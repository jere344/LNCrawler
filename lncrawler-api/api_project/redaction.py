"""Best-effort scrubbing of credentials/PII before logs or GitHub issues.

Not a guarantee: it targets the common shapes (Authorization headers, tokens,
passwords, API keys, cookies, credentials in URLs, JWTs). Anything that reaches
a log line is assumed potentially public.
"""

import re

_SECRET_KEYS = (
    r"authorization|proxy-authorization|cookie|set-cookie|"
    r"password|passwd|pwd|secret|api[_-]?key|apikey|"
    r"access[_-]?token|refresh[_-]?token|auth[_-]?token|id[_-]?token|token|"
    r"private[_-]?key|client[_-]?secret"
)

# key: value / key=value (headers, kwargs, query strings)
_KV = re.compile(rf"(?i)\b({_SECRET_KEYS})\b(\s*[:=]\s*)(\S+)")
# Bearer/Token <value>
_AUTH = re.compile(r"(?i)\b(bearer|token)\s+([A-Za-z0-9._~+/=-]{8,})")
# Credentials in a URL: scheme://user:pass@host
_URL_CREDS = re.compile(r"(?i)(https?://[^:/@\s]+):([^@\s]+)@")
# JWT
_JWT = re.compile(r"\b[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")


def redact(text):
    if not text:
        return text
    text = str(text)
    text = _URL_CREDS.sub(r"\1:***@", text)
    text = _KV.sub(r"\1\2***", text)
    text = _AUTH.sub(r"\1 ***", text)
    text = _JWT.sub("***JWT***", text)
    return text
