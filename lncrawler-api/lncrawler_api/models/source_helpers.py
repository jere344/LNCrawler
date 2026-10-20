import os

from django.conf import settings


def truncate(value, max_length=500):
    if value and len(value) > max_length:
        return value[:max_length]
    return value


def resolve_output_path(*relative):
    """
    Resolve DB-relative path parts under ``LNCRAWL_OUTPUT_PATH`` and return the
    absolute path, or ``None`` if the result escapes the output root (e.g. a
    poisoned ``..`` segment). Valid paths are returned unchanged.
    """
    base = os.path.realpath(settings.LNCRAWL_OUTPUT_PATH)
    target = os.path.realpath(os.path.join(base, *relative))
    try:
        if os.path.commonpath([base, target]) != base:
            return None
    except ValueError:
        return None
    return target
