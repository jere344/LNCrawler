"""
Novel merge service.

Two ``Novel`` rows can describe the same story when their source folders were
named differently (for example "lord of the mysteries" and "lord of
mysteries"). Merging folds one novel into another: sources, stats, comments,
reviews and user data are reassigned, duplicate sources are collapsed, and a
``NovelAlias`` is recorded so a future crawl of the discarded name attaches to
the surviving novel instead of recreating the duplicate.

Everything runs inside a single transaction, and folder changes go through a
``novel_operations`` file journal: a failure reverses the database writes and
the folder moves together.
"""
import logging
import os
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Optional

from django.db import IntegrityError, transaction
from django.db.models import Q

from ..db_locks import lock_pks
from ..models.sources_models import refresh_adult_for_tags
from ..utils.slug import slugify
from ..utils.tag_utils import normalize_tag
from .manual_merge import pair_candidate, record_manual_merge, record_manual_rename
from ..models import (
    Candidate,
    Comment,
    Novel,
    NovelAlias,
    NovelBookmark,
    NovelFromSource,
    NovelRating,
    NovelSimilarity,
    ReadingHistory,
    ReadingListItem,
    Review,
    Tag,
    TagAlias,
)
from .novel_operations import (
    FileOperationError,
    dedupe_source,
    file_journal,
    find_duplicate,
    move_source_to_novel,
    recount_comment_count,
    source_completeness,
)

logger = logging.getLogger('lncrawler_api')


class MergeError(Exception):
    """Raised when a merge request is invalid."""


@dataclass
class SourceMergePlan:
    source: NovelFromSource
    action: str  # 'move' | 'dedupe'
    winner: Optional[NovelFromSource] = None
    reason: str = ""


@dataclass
class MergePlan:
    source_novel: Novel
    target_novel: Novel
    move_files: bool = True
    alias_slugs: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    related_counts: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


def build_merge_plan(source_novel, target_novel, move_files=True):
    """Inspect a merge without changing anything, for the admin preview."""
    if source_novel.pk == target_novel.pk:
        raise MergeError("A novel cannot be merged into itself.")

    plan = MergePlan(
        source_novel=source_novel, target_novel=target_novel, move_files=move_files
    )

    for slug in {source_novel.slug, slugify(os.path.basename(source_novel.novel_path or ""))}:
        if slug and slug != target_novel.slug:
            plan.alias_slugs.append(slug)

    for source in source_novel.sources.all():
        duplicate = find_duplicate(target_novel, source)
        if duplicate is None:
            plan.sources.append(SourceMergePlan(source=source, action="move"))
            continue

        winner = source if source_completeness(source) > source_completeness(duplicate) else duplicate
        plan.sources.append(
            SourceMergePlan(
                source=source,
                action="dedupe",
                winner=winner,
                reason=(
                    f"Same external source ({source.external_source.source_name}); "
                    f"keeping the more complete copy"
                ),
            )
        )
        if winner is duplicate:
            plan.warnings.append(
                f"'{source.title}' has less content than the existing "
                f"'{duplicate.title}' and will be discarded."
            )

    plan.related_counts = {
        "ratings": NovelRating.objects.filter(novel=source_novel).count(),
        # Views live on sources now; they follow the sources as they are moved
        # or deduped, so there is nothing to migrate at the novel level.
        "comments": Comment.objects.filter(novel=source_novel).count(),
        "reviews": Review.objects.filter(novel=source_novel).count(),
        "bookmarks": NovelBookmark.objects.filter(novel=source_novel).count(),
        "reading_history": ReadingHistory.objects.filter(novel=source_novel).count(),
        "reading_list_items": ReadingListItem.objects.filter(novel=source_novel).count(),
        "similarities": NovelSimilarity.objects.filter(
            from_novel=source_novel
        ).count()
        + NovelSimilarity.objects.filter(to_novel=source_novel).count(),
    }
    return plan


def _novel_completeness(novel):
    """Best source completeness across a novel, as a comparable (content, total)."""
    best = (0, 0)
    for source in novel.sources.all():
        complete = source_completeness(source)
        candidate = (complete[0], complete[1])
        if candidate > best:
            best = candidate
    return best


def pick_merge_survivor(a, b):
    """Choose which novel survives a merge.

    Prefer the novel holding the most complete source (most readable chapters),
    then the one with more sources, then the lower id for stability. This keeps
    the copy with the most content and discards the thinner duplicate.
    """
    if a is None:
        return b
    if b is None:
        return a
    comp_a, comp_b = _novel_completeness(a), _novel_completeness(b)
    if comp_a != comp_b:
        return a if comp_a > comp_b else b
    count_a, count_b = a.sources.count(), b.sources.count()
    if count_a != count_b:
        return a if count_a > count_b else b
    return a if str(a.pk) <= str(b.pk) else b


def _record_aliases(source_novel, target_novel):
    # Anything already redirecting to the discarded novel now points at target.
    NovelAlias.objects.filter(novel=source_novel).update(novel=target_novel)
    slugs = {source_novel.slug, slugify(os.path.basename(source_novel.novel_path or ""))}
    for slug in slugs:
        if slug and slug != target_novel.slug:
            NovelAlias.objects.update_or_create(
                slug=slug, defaults={"novel": target_novel}
            )


def _merge_novel_ratings(source, target):
    """Move the source's ratings onto ``target``, keeping one rating per reader.

    The database allows one logged-in rating per (novel, user) and one anonymous
    rating per (novel, ip_address). When both novels rated the same user, the
    newer rating is kept and the other is deleted before the move, so the
    constraint never trips. Anonymous rows are compared by IP against the
    target's anonymous rows only; a NULL IP never matches, so it always moves.
    Anything not moved is deleted with the source.
    """
    target_users = {
        rating.user_id: rating
        for rating in NovelRating.objects.filter(novel=target, user__isnull=False)
    }
    target_ips = set(
        NovelRating.objects.filter(novel=target, user__isnull=True)
        .exclude(ip_address__isnull=True)
        .values_list("ip_address", flat=True)
    )

    for rating in NovelRating.objects.filter(novel=source).order_by("pk"):
        if rating.user_id is not None:
            existing = target_users.get(rating.user_id)
            if existing is not None:
                if existing.updated_at >= rating.updated_at:
                    # Ties keep the target's rating.
                    continue
                existing.delete()
            target_users[rating.user_id] = rating
        elif rating.ip_address is not None:
            if rating.ip_address in target_ips:
                continue
            target_ips.add(rating.ip_address)
        # A queryset update does not bump auto_now, so the rating keeps its time.
        NovelRating.objects.filter(pk=rating.pk).update(novel=target)

    NovelRating.objects.filter(novel=source).delete()


def _merge_similarities(source, target):
    """Remap similarities onto target, dropping self-links and duplicates.

    Remapped row by row because a bulk UPDATE can collide with an existing
    ``(from_novel, to_novel)`` pair on the unique constraint and abort the whole
    merge. Rows that would duplicate an existing pair are dropped instead.
    """
    existing = set(
        NovelSimilarity.objects.filter(
            Q(from_novel=target) | Q(to_novel=target)
        ).values_list("from_novel_id", "to_novel_id")
    )

    for similarity in NovelSimilarity.objects.filter(
        Q(from_novel=source) | Q(to_novel=source)
    ):
        remapped = (
            target.pk if similarity.from_novel_id == source.pk else similarity.from_novel_id,
            target.pk if similarity.to_novel_id == source.pk else similarity.to_novel_id,
        )
        if remapped[0] == remapped[1] or remapped in existing:
            similarity.delete()
            continue
        similarity.from_novel_id, similarity.to_novel_id = remapped
        similarity.save(update_fields=["from_novel", "to_novel"])
        existing.add(remapped)


def _source_row_wins(source_value, target_value):
    """Whether the incoming row's value beats the target's. ``None`` always loses."""
    if source_value is None:
        return False
    if target_value is None:
        return True
    return source_value > target_value


def _merge_user_scoped(source, target, model, newer_field=None):
    """Move rows unique on (novel, user); on conflict keep one of the two.

    Without ``newer_field`` the target's row wins. With it, the row with the
    greater value wins and ties go to the target. The losing row is deleted
    before the winner moves, so the unique constraint never trips. Moves use
    ``.update()`` so ``auto_now`` fields such as ``ReadingHistory.last_read_at``
    keep their real timestamps.
    """
    target_rows = {row.user_id: row for row in model.objects.filter(novel=target)}
    for row in model.objects.filter(novel=source).order_by("pk"):
        existing = target_rows.get(row.user_id)
        if existing is not None:
            wins = newer_field is not None and _source_row_wins(
                getattr(row, newer_field), getattr(existing, newer_field)
            )
            if not wins:
                row.delete()
                continue
            existing.delete()
        model.objects.filter(pk=row.pk).update(novel=target)
    model.objects.filter(novel=source).delete()


def _merge_reading_list_items(source, target):
    target_lists = set(
        ReadingListItem.objects.filter(novel=target).values_list(
            "reading_list_id", flat=True
        )
    )
    ReadingListItem.objects.filter(novel=source).exclude(
        reading_list_id__in=target_lists
    ).update(novel=target)
    ReadingListItem.objects.filter(novel=source).delete()


def merge_novels(source_novel, target_novel, move_files=True, return_moves=False, candidate=None):
    """Merge ``source_novel`` into ``target_novel`` and delete the former.

    The database writes and the folder changes succeed or fail together. Sources
    of one site that are different works coexist: each keeps its own folder.

    With ``return_moves`` the result is ``(target_novel, moves)``, where ``moves``
    lists the source ids moved over as they were and the ids folded into the
    target's copies. The candidate undo entry is built from it.

    ``candidate`` is the one being applied, which is left alone. Other open novel_merge
    candidates naming the source are deleted. Without a candidate (a manual merge) the
    pair's candidate, if any, is recorded as applied by a human.
    """
    if source_novel.pk == target_novel.pk:
        raise MergeError("A novel cannot be merged into itself.")

    source_pk = source_novel.pk
    source_sources = list(source_novel.sources.all())
    moved_ids, deduped_ids = [], []
    # The source is gone after the merge: its undo data is read first.
    snapshot = {
        "title": source_novel.title,
        "slug": source_novel.slug,
        "is_dmca": source_novel.is_dmca,
        "added_by": source_novel.added_by_id,
    }

    try:
        with file_journal() as files:
            with transaction.atomic():
                # Alias first, so the redirect never points at a deleted novel.
                _record_aliases(source_novel, target_novel)

                for source in source_sources:
                    duplicate = find_duplicate(target_novel, source)
                    if duplicate is None:
                        move_source_to_novel(source, target_novel, move_files, files=files)
                        moved_ids.append(source.pk)
                    elif source_completeness(source) > source_completeness(duplicate):
                        # Keep the incoming copy: fold the target's weaker copy into it
                        # first, freeing the (novel, source_url) slot, then repoint.
                        dedupe_source(
                            duplicate, source, move_files, files=files,
                            dest_novel=target_novel,
                        )
                        deduped_ids.append(duplicate.pk)
                        move_source_to_novel(source, target_novel, move_files, files=files)
                        moved_ids.append(source.pk)
                    else:
                        # Keep the existing target copy: drop the incoming one.
                        dedupe_source(
                            source, duplicate, move_files, files=files,
                            dest_novel=target_novel,
                        )
                        deduped_ids.append(source.pk)

                _merge_novel_ratings(source_novel, target_novel)
                _merge_similarities(source_novel, target_novel)

                # Novel-level comments only; chapter comments follow their sources.
                Comment.objects.filter(novel=source_novel).update(novel=target_novel)

                # Newest data wins on conflict: the later review, and the most
                # recently read history row, whichever novel it came from.
                _merge_user_scoped(source_novel, target_novel, Review, newer_field="updated_at")
                _merge_user_scoped(source_novel, target_novel, NovelBookmark)
                _merge_user_scoped(
                    source_novel, target_novel, ReadingHistory, newer_field="last_read_at"
                )
                _merge_reading_list_items(source_novel, target_novel)

                if candidate is None:
                    # Recorded before the drop below, so the pair's own open row is not deleted.
                    record_manual_merge(
                        Candidate.KIND_NOVEL_MERGE, [source_pk, target_novel.pk],
                        [snapshot["title"], target_novel.title],
                        {
                            "type": "novel_merge",
                            "source_id": str(source_pk),
                            "target_id": str(target_novel.pk),
                            "moved_source_ids": moved_ids,
                            **snapshot,
                        },
                        row=pair_candidate(Candidate.KIND_NOVEL_MERGE, [source_pk, target_novel.pk]),
                    )
                source_novel.delete()
                Candidate.drop_open_naming(
                    [source_pk], kinds=[Candidate.KIND_NOVEL_MERGE],
                    exclude_pk=candidate.pk if candidate is not None else None,
                )
                recount_comment_count(target_novel)
                files.schedule()
    except FileOperationError as exc:
        raise MergeError(str(exc)) from exc

    logger.info(
        "Merged novel '%s' (%s) into '%s' (%s)",
        source_novel.title, source_novel.slug, target_novel.title, target_novel.slug,
    )
    if return_moves:
        return target_novel, {"moved_source_ids": moved_ids, "deduped_source_ids": deduped_ids}
    return target_novel


def fold_tag(source_tag, target_tag, candidate=None):
    """Fold ``source_tag`` into ``target_tag``. Returns the undo entry of the change.

    The caller holds the transaction. Every source tagged with the duplicate is
    retagged, and a ``TagAlias`` records the discarded name so a future import of it
    resolves to the target instead of recreating the duplicate. The entry lists what
    moved, so the change can be reversed (``undo_tag_entry``).

    ``candidate`` is the one being applied, which is left alone. Other open tag_merge and
    tag_r18 candidates naming the source are deleted.
    """
    if source_tag.pk == target_tag.pk:
        raise MergeError("A tag cannot be merged into itself.")

    name = source_tag.name
    source_id = source_tag.pk

    # Lock both rows before reading links: a concurrent import must not attach
    # new sources to the source tag between the read and the delete.
    if len(lock_pks(Tag, [source_tag.pk, target_tag.pk])) != 2:
        raise MergeError("A tag was merged away concurrently; reload and try again.")

    source_ids = list(source_tag.novels.values_list("pk", flat=True))
    target_ids = set(target_tag.novels.values_list("pk", flat=True))
    moved_alias_ids = list(
        TagAlias.objects.filter(tag=source_tag).values_list("pk", flat=True)
    )
    TagAlias.objects.filter(pk__in=moved_alias_ids).update(tag=target_tag)
    target_tag.novels.add(*source_ids)
    source_was_adult, target_was_adult = source_tag.is_adult, target_tag.is_adult
    if source_tag.is_adult and not target_tag.is_adult:
        # The merged-into tag keeps the R18 flag so its novels stay adult.
        target_tag.is_adult = True
        target_tag.save(update_fields=["is_adult"])
    if target_tag.is_adult:
        refresh_adult_for_tags([target_tag.pk])
    source_tag.delete()
    Candidate.drop_open_naming(
        [source_id], kinds=[Candidate.KIND_TAG_MERGE, Candidate.KIND_TAG_R18],
        exclude_pk=candidate.pk if candidate is not None else None,
    )
    TagAlias.objects.update_or_create(name=name, defaults={"tag": target_tag})
    logger.info("Merged tag '%s' into '%s'", name, target_tag.name)
    return {
        "type": "tag_merge",
        "source_id": source_id,
        "source_name": name,
        "target_id": target_tag.pk,
        "target_name": target_tag.name,
        "all_source_ids": source_ids,
        "added_source_ids": [pk for pk in source_ids if pk not in target_ids],
        "moved_alias_ids": moved_alias_ids,
        "source_was_adult": source_was_adult,
        "target_was_adult": target_was_adult,
    }


def merge_tags(source_tag, target_tag):
    """Fold ``source_tag`` into ``target_tag`` (``fold_tag``) and record it as an applied candidate.

    The undo entry lives on the pair's tag_merge candidate, which a human applied (see
    ``manual_merge.record_manual_merge``).
    """
    with transaction.atomic():
        # Passed to fold_tag as the candidate it leaves alone, so its open row is not deleted.
        pks = [source_tag.pk, target_tag.pk]  # read before fold_tag deletes the source
        pair = pair_candidate(Candidate.KIND_TAG_MERGE, pks)
        entry = fold_tag(source_tag, target_tag, candidate=pair)
        record_manual_merge(
            Candidate.KIND_TAG_MERGE, pks, [entry["source_name"], entry["target_name"]], entry, row=pair,
        )
    return target_tag


def rename_tag(tag, new_name):
    """Give ``tag`` a new name (``apply_rename``) and record it as an applied candidate. Returns the tag."""
    with transaction.atomic():
        entry = apply_rename(tag, new_name)
        if entry is not None:
            record_manual_rename(tag.pk, entry)
    return tag


def apply_rename(tag, new_name):
    """Give ``tag`` a new name, keeping the old name as an alias. Returns the undo entry.

    Returns None when the name does not change. Raises ``MergeError`` when another
    tag, or an alias of another tag, already has the new name's key, or when the save
    loses a race with such a tag. The caller should merge into that tag instead.
    """
    new_name = new_name.strip()[: Tag._meta.get_field("name").max_length]
    old_name = tag.name
    if new_name == old_name:
        return None

    key = normalize_tag(new_name)
    if Tag.objects.filter(normalized=key).exclude(pk=tag.pk).exists():
        raise MergeError(f"Another tag already matches '{new_name}'; merge into it instead.")
    stray = TagAlias.objects.filter(normalized=key).exclude(tag_id=tag.pk).select_related("tag").first()
    if stray is not None:
        raise MergeError(
            f"'{new_name}' is already an alias of '{stray.tag.name}'; merge into it instead."
        )

    with transaction.atomic():
        if lock_pks(Tag, [tag.pk]) != {tag.pk}:
            raise MergeError(f"'{old_name}' was merged away; reload and try again.")
        try:
            # Nested savepoint: an IntegrityError rolls back only this write, and the
            # caller still gets a MergeError from the outer block.
            with transaction.atomic():
                # Same key (case/accent/plural only): the old name already resolves to this tag.
                if key != tag.normalized:
                    TagAlias.objects.update_or_create(name=old_name, defaults={"tag": tag})
                tag.name = new_name
                # The stored vector described the old name; drop it so it is re-embedded.
                tag.embedding = None
                tag.embedding_model = ""
                tag.save()
        except IntegrityError as exc:
            raise MergeError(
                f"'{new_name}' conflicts with an existing tag or alias; merge into it instead."
            ) from exc

    logger.info("Renamed tag '%s' to '%s'", old_name, new_name)
    return {"type": "tag_rename", "target_id": tag.pk, "target_name": new_name, "renamed_from": old_name}


def _undo_merge(merge):
    target = merge.target
    key = normalize_tag(merge.source_name)
    if key == target.normalized:
        # Same key as the target: a separate row cannot coexist with it, and the
        # alias already resolves the old name to the target.
        raise MergeError(
            f"'{merge.source_name}' has the same key as '{target.name}' and cannot "
            "be restored as a separate tag."
        )

    # Reuse a tag that already carries the key (created since the merge), else
    # recreate the merged-away one.
    try:
        source, _ = Tag.objects.get_or_create(normalized=key, defaults={"name": merge.source_name})
    except IntegrityError as exc:
        raise MergeError(f"'{merge.source_name}' could not be restored: {exc}") from exc

    # Aliases first, then drop the alias the merge itself created for the old name
    # (an alias that was moved back to the source keeps its row).
    TagAlias.objects.filter(pk__in=merge.moved_alias_ids, tag=target).update(tag=source)
    TagAlias.objects.filter(name=merge.source_name, tag=target).delete()

    restored = list(
        NovelFromSource.objects.filter(pk__in=merge.all_source_ids).values_list("pk", flat=True)
    )
    source.novels.add(*restored)
    target.novels.remove(*merge.added_source_ids)

    # Put the R18 flags back as they were before the merge, then re-derive the
    # adult flag of every source either tag touches (both directions).
    for tag, was_adult in ((source, merge.source_was_adult), (target, merge.target_was_adult)):
        if was_adult is not None and tag.is_adult != was_adult:
            tag.is_adult = was_adult
            tag.save(update_fields=["is_adult"])
    refresh_adult_for_tags([source.pk, target.pk])
    return source


def _undo_rename(merge):
    tag = merge.target
    old_name = merge.renamed_from
    key = normalize_tag(old_name)
    if Tag.objects.filter(normalized=key).exclude(pk=tag.pk).exists():
        raise MergeError(f"Cannot restore '{old_name}': another tag already uses that name.")

    if key != normalize_tag(merge.target_name):
        TagAlias.objects.filter(name=old_name, tag=tag).delete()
    tag.name = old_name
    tag.embedding = None
    tag.embedding_model = ""
    tag.save()


def undo_tag_entry(entry):
    """Reverse one undo entry (``fold_tag`` or ``apply_rename``) and return the restored ids.

    The restored tag of a merge is a new row, so the returned ``source_id`` can differ
    from the entry's. Callers repoint the ids they hold. Refused when the target is
    gone or the restored key is taken.
    """
    with transaction.atomic():
        # The target and (for a merge) the tag holding the source's key, locked in one
        # statement ordered by pk. The target is also looked up by its name's key: undoing
        # a later merge of it (A->B then B->C, undone newest first) recreates it under a new pk.
        target_key = normalize_tag(entry["target_name"])
        filters = Q(pk=entry["target_id"]) | Q(normalized=target_key)
        if entry["type"] == "tag_merge":
            filters |= Q(normalized=normalize_tag(entry["source_name"]))
        locked = list(Tag.objects.select_for_update().filter(filters).order_by("pk"))
        target = next((tag for tag in locked if tag.pk == entry["target_id"]), None)
        if target is None:
            target = next((tag for tag in locked if tag.normalized == target_key), None)
        if target is None:
            raise MergeError("The target tag was merged away or deleted; reload and try again.")

        if entry["type"] == "tag_rename":
            _undo_rename(SimpleNamespace(
                target=target,
                renamed_from=entry["renamed_from"],
                target_name=entry["target_name"],
            ))
            return {"target_id": target.pk}
        source = _undo_merge(SimpleNamespace(
            target=target,
            source_name=entry["source_name"],
            moved_alias_ids=entry["moved_alias_ids"],
            all_source_ids=entry["all_source_ids"],
            added_source_ids=entry["added_source_ids"],
            source_was_adult=entry["source_was_adult"],
            target_was_adult=entry["target_was_adult"],
        ))
    logger.info("Undid tag entry %s", entry)
    return {"source_id": source.pk, "target_id": target.pk}
