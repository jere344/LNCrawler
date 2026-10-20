"""Helpers shared by the novel, tag and author merge code.

Pair signatures and ordering, and the undo lookups that the tag and author
merges both need. None of them import models, so the model modules can use
them without a circular import. Row locks live in ``db_locks``.
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


def find_later_merge(model, merge):
    """The first live merge of ``merge``'s target name that was made after it, or None."""
    return (
        model.objects.filter(
            source_name=merge.target_name,
            undone_at__isnull=True,
            created_at__gt=merge.created_at,
        )
        .exclude(pk=merge.pk)
        .order_by("created_at")
        .first()
    )


def repoint_orphaned_merges(model, name, target):
    """Point the live merges whose target was ``name`` (now merged away) at ``target``.

    Used when the merged-away record is restored, so those later merges can be
    undone in turn.
    """
    model.objects.filter(
        target__isnull=True, target_name=name, undone_at__isnull=True
    ).update(target=target)
