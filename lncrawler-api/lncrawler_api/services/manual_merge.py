"""Record a merge a person made by hand as a candidate, so the pair is not proposed again.

A manual merge (admin, no candidate) of a pair that already has a candidate turns that
candidate into an applied one decided by a human: its verdict is kept and the undo entry
is appended. Otherwise a new applied candidate is created. Undo and the finders then see
the pair as they would a merge the LLM applied.

Imports only models and ``merge_common``, so the merge services can use it.
"""
import uuid

from django.utils import timezone

from ..models import Candidate
from .merge_common import sorted_pk_signature


def _json_id(pk):
    """Novel ids are UUIDs, stored as strings; the other ids are ints."""
    return str(pk) if isinstance(pk, uuid.UUID) else pk


def pair_candidate(kind, pks):
    """The candidate of ``kind`` that names this pair, in any status, or None."""
    return Candidate.objects.filter(kind=kind, signature=sorted_pk_signature(pks)).first()


def record_manual_rename(tag_pk, entry):
    """Record a tag rename made by hand as an applied candidate, so it can be undone.

    A rename names one tag, not a pair: each one gets its own candidate.
    """
    return Candidate.objects.create(
        kind=Candidate.KIND_TAG_MERGE,
        signature=f"rename:{tag_pk}:{uuid.uuid4().hex}",
        target_ids=[tag_pk],
        target_names=[entry["renamed_from"], entry["target_name"]],
        status=Candidate.STATUS_APPLIED,
        decided_by=Candidate.DECIDED_HUMAN,
        decided_at=timezone.now(),
        undo=[entry],
    )


def record_manual_merge(kind, pks, names, entry, row=None):
    """Make the pair's candidate applied by a human, with ``entry`` appended to its undo list.

    ``row`` is the candidate from ``pair_candidate``; without one a new candidate is created.
    Returns the candidate.
    """
    now = timezone.now()
    if row is None:
        return Candidate.objects.create(
            kind=kind,
            signature=sorted_pk_signature(pks),
            target_ids=[_json_id(pk) for pk in pks],
            target_names=list(names),
            status=Candidate.STATUS_APPLIED,
            decided_by=Candidate.DECIDED_HUMAN,
            decided_at=now,
            undo=[entry],
        )
    row.status = Candidate.STATUS_APPLIED
    row.decided_by = Candidate.DECIDED_HUMAN
    row.decided_at = now
    row.undo = [*row.undo, entry]
    row.claimed_at = None
    row.save(update_fields=["status", "decided_by", "decided_at", "undo", "claimed_at", "updated_at"])
    return row
