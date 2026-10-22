"""Pairs of one kind that must not be proposed again: the blocks the finders read.

A pair is blocked when a candidate naming both members was rejected or undone. Merges
made since then move a member: a pair blocked on ``A`` is blocked on ``B`` once ``A``
was merged into ``B``. The live merges are the applied candidates' undo entries.

Pks are compared as strings (novel ids are UUIDs, the others ints): ``pair_key``
gives the one spelling every caller uses.
"""
from itertools import combinations

from ..models import Candidate
from .merge_common import ordered_pair

# A chain of merges longer than this is treated as a cycle and stops being followed.
MAX_CHAIN = 100


def pair_key(a, b):
    """The unordered pair ``(a, b)`` as a tuple of string pks, sorted."""
    return ordered_pair(str(a), str(b))


def _forward_merges(kind):
    """``{source pk: target pk}`` of the live merges of ``kind``, as strings."""
    forward = {}
    rows = Candidate.objects.filter(kind=kind, status=Candidate.STATUS_APPLIED).values_list("undo", flat=True)
    for entries in rows:
        for entry in entries or []:
            # A merge undone before the candidate was applied again no longer stands.
            if entry.get("undone_at"):
                continue
            if "source_id" in entry and "target_id" in entry:
                forward[str(entry["source_id"])] = str(entry["target_id"])
    return forward


def _follow(pk, forward):
    """The pk the given pk stands for now, after the merges made since."""
    current = str(pk)
    for _ in range(MAX_CHAIN):
        if current not in forward:
            break
        current = forward[current]
    return current


def blocked_pairs(kind):
    """The set of ``pair_key`` pairs of ``kind`` that must not be proposed."""
    forward = _forward_merges(kind)
    blocked = set()
    rows = Candidate.objects.filter(
        kind=kind, status__in=(Candidate.STATUS_REJECTED, Candidate.STATUS_UNDONE),
    ).values_list("status", "target_ids", "verdict", "undo")
    for status, target_ids, verdict, undo in rows:
        for group in _blocked_groups(kind, status, target_ids, verdict, undo):
            members = [_follow(pk, forward) for pk in group]
            for a, b in combinations(members, 2):
                if a != b:
                    blocked.add(pair_key(a, b))
    return blocked


def _blocked_groups(kind, status, target_ids, verdict, undo):
    """The groups of ids a rejected or undone candidate rules out.

    A pair kind rules out its pair. A tag cluster only rules out what was put together:
    - undone: every two members of each merged set, under the ids the undo restored;
    - rejected after an LLM answer: the pairs inside the sets the LLM proposed (the
      ones a human saw); a cluster with no set blocks nothing;
    - rejected with no LLM answer (a pair refused by hand): all of its tags.
    """
    if kind != Candidate.KIND_TAG_MERGE:
        return [target_ids or []]
    if status == Candidate.STATUS_UNDONE:
        merged = {}
        for entry in undo or []:
            if entry.get("type") != "tag_merge":
                continue
            target = entry.get("restored_target_id", entry.get("target_id"))
            source = entry.get("restored_source_id", entry.get("source_id"))
            merged.setdefault(target, {target}).add(source)
        return [[pk for pk in group if pk is not None] for group in merged.values()]
    if isinstance(verdict, dict) and "sets" in verdict:
        return [
            proposed.get("members") or []
            for proposed in verdict.get("sets") or [] if isinstance(proposed, dict)
        ]
    return [target_ids or []]
