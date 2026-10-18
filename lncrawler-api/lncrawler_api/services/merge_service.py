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
from itertools import combinations
from typing import Optional

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from ..models.sources_models import refresh_adult_for_tags
from ..utils.slug import slugify
from ..utils.tag_utils import normalize_tag
from ..models import (
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
    TagCluster,
    TagMerge,
    TagNoMerge,
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

    @property
    def has_warnings(self):
        return bool(self.warnings)


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


def merge_novels(source_novel, target_novel, move_files=True):
    """Merge ``source_novel`` into ``target_novel`` and delete the former.

    The database writes and the folder changes succeed or fail together. Sources
    of one site that are different works coexist: each keeps its own folder.
    """
    if source_novel.pk == target_novel.pk:
        raise MergeError("A novel cannot be merged into itself.")

    source_sources = list(source_novel.sources.all())

    try:
        with file_journal() as files:
            with transaction.atomic():
                # Alias first, so the redirect never points at a deleted novel.
                _record_aliases(source_novel, target_novel)

                for source in source_sources:
                    duplicate = find_duplicate(target_novel, source)
                    if duplicate is None:
                        move_source_to_novel(source, target_novel, move_files, files=files)
                    elif source_completeness(source) > source_completeness(duplicate):
                        # Keep the incoming copy: fold the target's weaker copy into it
                        # first, freeing the (novel, source_url) slot, then repoint.
                        dedupe_source(
                            duplicate, source, move_files, files=files,
                            dest_novel=target_novel,
                        )
                        move_source_to_novel(source, target_novel, move_files, files=files)
                    else:
                        # Keep the existing target copy: drop the incoming one.
                        dedupe_source(
                            source, duplicate, move_files, files=files,
                            dest_novel=target_novel,
                        )

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

                source_novel.delete()
                recount_comment_count(target_novel)
                files.schedule()
    except FileOperationError as exc:
        raise MergeError(str(exc)) from exc

    logger.info(
        "Merged novel '%s' (%s) into '%s' (%s)",
        source_novel.title, source_novel.slug, target_novel.title, target_novel.slug,
    )
    return target_novel


def lock_tags(pks):
    """Row-lock tags in one statement, ordered by pk, and return the pks still present.

    Callers must be inside a transaction. Taking every lock a unit of work needs
    in one sorted call keeps two concurrent units from waiting on each other.
    """
    pks = sorted(set(pks))
    if not pks:
        return set()
    return set(
        Tag.objects.select_for_update()
        .filter(pk__in=pks)
        .order_by("pk")
        .values_list("pk", flat=True)
    )


def merge_tags(source_tag, target_tag, cluster=None):
    """Fold ``source_tag`` into ``target_tag`` and remember the old name.

    Every source tagged with the duplicate is retagged, and a ``TagAlias``
    records the discarded name so a future import of it resolves to the target
    instead of recreating the duplicate. The change is stored as a ``TagMerge``
    so ``undo_tag_merge`` can reverse it.
    """
    if source_tag.pk == target_tag.pk:
        raise MergeError("A tag cannot be merged into itself.")

    name = source_tag.name

    with transaction.atomic():
        # Lock both rows before reading links: a concurrent import must not attach
        # new sources to the source tag between the read and the delete.
        if len(lock_tags([source_tag.pk, target_tag.pk])) != 2:
            raise MergeError("A tag was merged away concurrently; reload and try again.")

        source_ids = list(source_tag.novels.values_list("pk", flat=True))
        target_ids = set(target_tag.novels.values_list("pk", flat=True))
        moved_alias_ids = list(
            TagAlias.objects.filter(tag=source_tag).values_list("pk", flat=True)
        )
        TagAlias.objects.filter(pk__in=moved_alias_ids).update(tag=target_tag)
        target_tag.novels.add(*source_ids)
        _move_no_merge_pairs(source_tag, target_tag)
        source_was_adult, target_was_adult = source_tag.is_adult, target_tag.is_adult
        if source_tag.is_adult and not target_tag.is_adult:
            # The merged-into tag keeps the R18 flag so its novels stay adult.
            target_tag.is_adult = True
            target_tag.save(update_fields=["is_adult"])
        if target_tag.is_adult:
            refresh_adult_for_tags([target_tag.pk])
        source_tag.delete()
        TagAlias.objects.update_or_create(name=name, defaults={"tag": target_tag})
        TagMerge.objects.create(
            cluster=cluster,
            kind=TagMerge.KIND_MERGE,
            source_name=name,
            target=target_tag,
            target_name=target_tag.name,
            all_source_ids=source_ids,
            added_source_ids=[pk for pk in source_ids if pk not in target_ids],
            moved_alias_ids=moved_alias_ids,
            source_was_adult=source_was_adult,
            target_was_adult=target_was_adult,
        )

    logger.info("Merged tag '%s' into '%s'", name, target_tag.name)
    return target_tag


def _move_no_merge_pairs(source_tag, target_tag):
    """Re-point the source's "not mergeable" pairs at the target.

    A pair that would become a self-pair, or duplicate one the target already has,
    is dropped instead.
    """
    for row in list(TagNoMerge.objects.filter(Q(tag_a=source_tag) | Q(tag_b=source_tag))):
        other = row.tag_b_id if row.tag_a_id == source_tag.pk else row.tag_a_id
        row.delete()
        if other == target_tag.pk:
            continue
        if TagNoMerge.objects.filter(
            Q(tag_a_id=target_tag.pk, tag_b_id=other) | Q(tag_a_id=other, tag_b_id=target_tag.pk)
        ).exists():
            continue
        TagNoMerge.objects.create(tag_a_id=target_tag.pk, tag_b_id=other)


def rename_tag(tag, new_name, cluster=None):
    """Give ``tag`` a new name, keeping the old name as an alias.

    Raises ``MergeError`` when another tag, or an alias of another tag, already
    has the new name's key, or when the save loses a race with such a tag. The
    caller should merge into that tag instead.
    """
    new_name = new_name.strip()[: Tag._meta.get_field("name").max_length]
    old_name = tag.name
    if new_name == old_name:
        return tag

    key = normalize_tag(new_name)
    if Tag.objects.filter(normalized=key).exclude(pk=tag.pk).exists():
        raise MergeError(f"Another tag already matches '{new_name}'; merge into it instead.")
    stray = TagAlias.objects.filter(normalized=key).exclude(tag_id=tag.pk).select_related("tag").first()
    if stray is not None:
        raise MergeError(
            f"'{new_name}' is already an alias of '{stray.tag.name}'; merge into it instead."
        )

    with transaction.atomic():
        if lock_tags([tag.pk]) != {tag.pk}:
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
        TagMerge.objects.create(
            cluster=cluster,
            kind=TagMerge.KIND_RENAME,
            source_name=old_name,
            target=tag,
            target_name=new_name,
            renamed_from=old_name,
        )

    logger.info("Renamed tag '%s' to '%s'", old_name, new_name)
    return tag


def block_tag_pair(tag_a_id, tag_b_id):
    """Record that two tags must never be proposed as duplicates again."""
    if tag_a_id == tag_b_id:
        return
    exists = TagNoMerge.objects.filter(
        Q(tag_a_id=tag_a_id, tag_b_id=tag_b_id) | Q(tag_a_id=tag_b_id, tag_b_id=tag_a_id)
    ).exists()
    if not exists:
        TagNoMerge.objects.create(tag_a_id=tag_a_id, tag_b_id=tag_b_id)


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

    # A later merge may have taken this name away (this tag was its target). Point
    # those records at the restored tag so they can be undone in turn.
    TagMerge.objects.filter(
        target__isnull=True, target_name=merge.source_name, undone_at__isnull=True
    ).update(target=source)

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


def undo_tag_merge(merge):
    """Reverse one ``TagMerge``: restore the merged-away tag or the old name."""
    if merge.undone_at is not None:
        raise MergeError("This change was already undone.")
    if merge.target is None:
        # The target was merged away later. Its own merge must be undone first.
        later = (
            TagMerge.objects.filter(
                source_name=merge.target_name,
                undone_at__isnull=True,
                created_at__gt=merge.created_at,
            )
            .exclude(pk=merge.pk)
            .order_by("created_at")
            .first()
        )
        if later is not None:
            raise MergeError(
                f"Undo the later merge of '{later.source_name}' into "
                f"'{later.target_name}' (#{later.pk}) first"
            )
        raise MergeError("The target tag no longer exists.")

    with transaction.atomic():
        # The target and (for a merge) the tag holding the source's key, in one
        # statement ordered by pk. Inside undo_tag_cluster these rows are already
        # locked by its single lock_tags call, so this is a no-op there.
        filters = Q(pk=merge.target_id)
        if merge.kind == TagMerge.KIND_MERGE:
            filters |= Q(normalized=normalize_tag(merge.source_name))
        locked = set(
            Tag.objects.select_for_update()
            .filter(filters)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        if merge.target_id not in locked:
            raise MergeError("The target tag was merged away; reload and try again.")

        if merge.kind == TagMerge.KIND_RENAME:
            _undo_rename(merge)
        else:
            _undo_merge(merge)
        merge.undone_at = timezone.now()
        merge.save(update_fields=["undone_at"])

    logger.info("Undid tag change: %s", merge)
    return merge


def undo_tag_cluster(cluster):
    """Undo every live change a cluster made and keep its members apart.

    Changes are reversed newest first, and each one is reloaded just before it is
    undone so links that a newer undo repaired (chained merges) are seen. Each
    merged set then gets a ``TagNoMerge`` pair for every two of its members, so
    the same proposal is not made again.
    """
    with transaction.atomic():
        merges = list(
            cluster.merges.filter(undone_at__isnull=True).order_by("-created_at", "-pk")
        )
        # Lock every target and every live source-key tag in one sorted call before
        # the first undo. Restored tags are new rows, so they need no lock.
        wanted = {merge.target_id for merge in merges if merge.target_id is not None}
        for merge in merges:
            if merge.kind == TagMerge.KIND_MERGE:
                key_pk = (
                    Tag.objects.filter(normalized=normalize_tag(merge.source_name))
                    .values_list("pk", flat=True)
                    .first()
                )
                if key_pk is not None:
                    wanted.add(key_pk)
        lock_tags(wanted)

        for merge in merges:
            merge.refresh_from_db()
            undo_tag_merge(merge)

        # Each undo can re-point older merges (chains), so reload every merge now and
        # read its final target. Restored sources have new ids: resolve them by key.
        sets = {}
        for merge in merges:
            merge.refresh_from_db()
            if merge.kind != TagMerge.KIND_MERGE:
                continue
            target_id = merge.target_id
            if target_id is None:
                found = Tag.objects.filter(normalized=normalize_tag(merge.target_name)).first()
                target_id = found.pk if found is not None else None
            if target_id is None:
                continue
            members = sets.setdefault(target_id, {target_id})
            source = Tag.objects.filter(normalized=normalize_tag(merge.source_name)).first()
            if source is not None:
                members.add(source.pk)
        for members in sets.values():
            for a, b in combinations(sorted(members), 2):
                block_tag_pair(a, b)

        cluster.status = TagCluster.STATUS_UNDONE
        cluster.save(update_fields=["status", "updated_at"])

    logger.info("Undid tag cluster %s", cluster.pk)
    return cluster
