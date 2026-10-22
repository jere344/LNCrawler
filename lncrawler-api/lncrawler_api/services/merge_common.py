"""Helpers shared by the novel, tag and author merge code.

Pair signatures and ordering, shared by the novel, tag and author merge code.
None of them import models, so the model modules can use them without a circular
import. Row locks live in ``db_locks``.
"""
import hashlib


def sorted_pk_signature(pks):
    """Stable hash of a set of pks, the same whatever their order."""
    return hashlib.sha1(",".join(str(pk) for pk in sorted(pks)).encode()).hexdigest()


def ordered_pair(a, b, key=lambda value: value):
    """Return ``(a, b)`` or ``(b, a)``, whichever sorts first by ``key`` (the value itself by default).

    With the default key the values are compared directly (UUIDs order like their hex string; ints numerically).
    """
    return (a, b) if key(a) <= key(b) else (b, a)
