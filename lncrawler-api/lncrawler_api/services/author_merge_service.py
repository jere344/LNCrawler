"""Author merge: fold one author into another, and undo it.

Mirrors ``merge_service.fold_tag`` and ``undo_tag_entry`` for authors. The finder
(``find_author_candidates``) proposes the pairs and the LLM judge (``AuthorMergeTask``)
decides them; ``merge_authors`` refuses a merge that would leave an alias name in use.
The undo entry of a merge is kept on its ``Candidate``.
"""
import logging

from django.db import transaction

from ..db_locks import lock_pks
from ..models import Author, AuthorAlias, Candidate, NovelFromSource
from ..utils.author_names import normalize_author
from .manual_merge import pair_candidate, record_manual_merge
from .merge_service import MergeError

logger = logging.getLogger("lncrawler_api.merge")


class AuthorMergeRefused(MergeError):
    """A merge that stays refused until the data changes: same author, alias name in use."""


def pick_target(a, b):
    """The author with more novel sources survives; a tie keeps the lower pk."""
    return min((a, b), key=lambda author: (-author.novels.count(), author.pk))


def merge_authors(source, target, candidate=None):
    """Fold ``source`` into ``target`` and remember the old name. Returns the undo entry.

    Every novel source credited to the duplicate is credited to the target, and an
    ``AuthorAlias`` records the discarded name so a future import of it resolves
    to the target. Open candidates (pending, review, error) that name the source are
    deleted. ``candidate`` is the one being applied, which is left alone.
    An admin merge (no candidate) is recorded as applied by a human on the pair's
    candidate, if any, or on a new one (``manual_merge.record_manual_merge``).
    """
    if source.pk == target.pk:
        raise AuthorMergeRefused("An author cannot be merged into itself.")
    if source.is_blocked or target.is_blocked:
        raise AuthorMergeRefused("blocked author")

    with transaction.atomic():
        # Lock both rows before reading links: a concurrent import must not credit
        # new sources to the source author between the read and the delete.
        locked = lock_pks(Author, [source.pk, target.pk])
        if len(locked) != 2:
            raise MergeError("An author was merged away concurrently; reload and try again.")

        source_name = source.name
        source_pk = source.pk
        # The alias for the old name must be new, so undo can delete it safely.
        if AuthorAlias.objects.filter(name=source_name).exclude(author=source).exists():
            raise AuthorMergeRefused("alias name already in use")
        source_ids = list(source.novels.values_list("pk", flat=True))
        target_ids = set(target.novels.values_list("pk", flat=True))
        moved_alias_ids = list(
            AuthorAlias.objects.filter(author=source).values_list("pk", flat=True)
        )
        AuthorAlias.objects.filter(pk__in=moved_alias_ids).update(author=target)
        target.novels.add(*source_ids)
        # The pair's own candidate is kept by the drop below: a manual merge records it as applied.
        pair = candidate if candidate is not None else pair_candidate(
            Candidate.KIND_AUTHOR_MERGE, [source_pk, target.pk]
        )
        source.delete()
        # Open pairs that name the source point at a missing author: they are deleted.
        Candidate.drop_open_naming(
            [source_pk], kinds=[Candidate.KIND_AUTHOR_MERGE],
            exclude_pk=pair.pk if pair is not None else None,
        )
        # Same key as the target: the target already resolves that name, no alias needed.
        alias_created = False
        if normalize_author(source_name) != target.normalized:
            _, alias_created = AuthorAlias.objects.update_or_create(
                name=source_name, defaults={"author": target}
            )
        entry = {
            "type": "author_merge",
            "source_id": source_pk,
            "source_name": source_name,
            "target_id": target.pk,
            "target_name": target.name,
            "source_ids": source_ids,
            "added_source_ids": [pk for pk in source_ids if pk not in target_ids],
            "moved_alias_ids": moved_alias_ids,
            "alias_created": alias_created,
        }
        if candidate is None:
            record_manual_merge(
                Candidate.KIND_AUTHOR_MERGE, [source_pk, target.pk],
                [source_name, target.name], entry, row=pair,
            )

    logger.info("Merged author '%s' into '%s'", source_name, target.name)
    return entry


def undo_author_entry(entry):
    """Reverse one undo entry of ``merge_authors``. Returns the ids the undo restored.

    The restored author keeps its old pk when it is free (it always is, as pks are
    not reused). Refused when the target is gone or blocked.
    """
    target = Author.objects.filter(pk=entry["target_id"]).first()
    if target is None:
        raise MergeError("The target author no longer exists.")
    if target.is_blocked:
        raise MergeError("The target author is blocked; unblock it first.")

    with transaction.atomic():
        locked = lock_pks(Author, [target.pk])
        if target.pk not in locked:
            raise MergeError("The target author was merged away; reload and try again.")

        source = Author.objects.create(pk=entry["source_id"], name=entry["source_name"])
        # Aliases first, then drop the alias the merge itself created for the old
        # name (an alias that was moved back to the source keeps its row).
        AuthorAlias.objects.filter(pk__in=entry["moved_alias_ids"], author=target).update(author=source)
        if entry["alias_created"]:
            AuthorAlias.objects.filter(name=entry["source_name"], author=target).delete()

        restored = list(
            NovelFromSource.objects.filter(pk__in=entry["source_ids"]).values_list("pk", flat=True)
        )
        source.novels.add(*restored)
        target.novels.remove(*entry["added_source_ids"])

    logger.info("Undid author merge of '%s' into '%s'", entry["source_name"], entry["target_name"])
    return {"source_id": source.pk, "target_id": target.pk}
