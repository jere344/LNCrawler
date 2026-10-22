"""Human decisions on candidates: apply, reject, redecide, undo and rejudge.

The LLM runner (``llm_tasks``) decides on its own. These functions serve a person,
through the admin or the API, and record ``decided_by`` human, except
``redecide_candidate``, which runs the LLM's verdict through the rules again (recorded
as decided by the LLM), and ``rejudge_candidate``, which puts a candidate back in the
LLM queue.
"""
import logging

from django.db import transaction
from django.utils import timezone

from ..models import Candidate, Novel, NovelFromSource, Tag
from ..models.sources_models import refresh_adult_for_tags
from . import llm_tasks
from .author_merge_service import undo_author_entry
from .merge_service import MergeError, undo_tag_entry
from .split_service import SplitError, split_novel
from .tag_merge_service import NeedsReview, PlanChanged

logger = logging.getLogger("lncrawler_api.merge")


class CandidateError(MergeError):
    """A human decision that the candidate's state or data does not allow."""


def _ensure_status(candidate, *statuses):
    if candidate.status not in statuses:
        raise CandidateError(
            f"This candidate is {candidate.status}; expected {' or '.join(statuses)}."
        )


def _lock(candidate):
    """The current row of ``candidate``, locked until the caller's transaction ends.

    The admin passes the row it loaded with the page: re-reading it under the lock makes
    the status and claim checks see what the runner or another reviewer wrote since.
    """
    row = Candidate.objects.select_for_update().filter(pk=candidate.pk).first()
    if row is None:
        raise CandidateError("This candidate no longer exists; reload the page.")
    return row


def _ensure_unclaimed(candidate):
    if candidate.claimed_at is not None:
        raise CandidateError("This candidate is being judged by the LLM; try again once the judgement is saved.")


def _mark(candidate, status, reason=""):
    _ensure_unclaimed(candidate)
    candidate.status = status
    candidate.decided_by = Candidate.DECIDED_HUMAN
    candidate.decided_at = timezone.now()
    candidate.reason = reason
    candidate.save(update_fields=["status", "decided_by", "decided_at", "reason", "updated_at"])


def _apply(candidate, decided_by=Candidate.DECIDED_HUMAN):
    """Make the change of ``candidate`` from its stored verdict and mark it applied.

    A refused change raises ``CandidateError`` and leaves the candidate as it was.
    A task with ``apply_in_transaction`` False takes the two-phase path.
    """
    _ensure_unclaimed(candidate)
    task = llm_tasks.REGISTRY[candidate.kind]
    if not task.apply_in_transaction:
        return _apply_two_phase(task, candidate, decided_by)
    try:
        with transaction.atomic():
            entries = task.apply_change(candidate, candidate.verdict or {})
    except (MergeError, NeedsReview, PlanChanged) as exc:
        raise CandidateError(str(exc)) from exc
    candidate.undo = [*candidate.undo, *entries]
    candidate.status = Candidate.STATUS_APPLIED
    candidate.decided_by = decided_by
    candidate.decided_at = timezone.now()
    candidate.save(update_fields=["undo", "status", "decided_by", "decided_at", "updated_at"])
    return candidate


def _apply_two_phase(task, candidate, decided_by=Candidate.DECIDED_HUMAN):
    """Apply a candidate whose change runs outside any transaction (``apply_in_transaction`` False).

    Phase 1 claims the candidate under its lock, so the LLM runner and a second reviewer
    leave it alone. Phase 2 runs the change with no lock held. Phase 3 writes the outcome
    if the claim is still ours.
    """
    token = timezone.now()
    with transaction.atomic():
        locked = Candidate.objects.select_for_update().filter(pk=candidate.pk).first()
        if locked is None or locked.status != candidate.status:
            raise CandidateError("This candidate changed while it was being decided; reload it.")
        _ensure_unclaimed(locked)
        Candidate.objects.filter(pk=candidate.pk).update(claimed_at=token)
    try:
        entries = task.apply_change(candidate, candidate.verdict or {})
    except (MergeError, NeedsReview, PlanChanged) as exc:
        Candidate.objects.filter(pk=candidate.pk, claimed_at=token).update(claimed_at=None)
        raise CandidateError(str(exc)) from exc
    except Exception:
        Candidate.objects.filter(pk=candidate.pk, claimed_at=token).update(claimed_at=None)
        raise
    now = timezone.now()
    # The change ran: it is recorded whatever happened to the claim, or it could not be undone.
    written = Candidate.objects.filter(pk=candidate.pk).update(
        claimed_at=None,
        undo=[*candidate.undo, *entries],
        status=Candidate.STATUS_APPLIED,
        decided_by=decided_by,
        decided_at=now,
        updated_at=now,
    )
    if not written:
        logger.error("Candidate %s (%s) vanished while applying; undo entries %s", candidate.pk, candidate.kind, entries)
        raise CandidateError("The change ran, but the candidate was deleted meanwhile; its undo entries are in the log.")
    candidate.refresh_from_db()
    return candidate


def apply_candidate(candidate):
    """Apply a candidate waiting in review, as the reviewer decided."""
    if not llm_tasks.REGISTRY[candidate.kind].apply_in_transaction:
        # The two-phase path locks and checks the row itself.
        _ensure_status(candidate, Candidate.STATUS_REVIEW)
        return _apply(candidate)
    with transaction.atomic():
        candidate = _lock(candidate)
        _ensure_status(candidate, Candidate.STATUS_REVIEW)
        return _apply(candidate)


def reject_candidate(candidate):
    """Reject a candidate waiting in review."""
    with transaction.atomic():
        candidate = _lock(candidate)
        _ensure_status(candidate, Candidate.STATUS_REVIEW)
        _mark(candidate, Candidate.STATUS_REJECTED)
    return candidate


def redecide_candidate(candidate):
    """Run the stored verdict of an LLM decision through the current rules again.

    Works on candidates in review or rejected whose decision the LLM made. The verdict
    stays as the LLM gave it; the threshold, the safeguards and the apply path are the
    current ones. The outcome is recorded as decided by the LLM.
    """
    task = llm_tasks.REGISTRY[candidate.kind]
    with transaction.atomic():
        candidate = _lock(candidate)
        _ensure_status(candidate, Candidate.STATUS_REVIEW, Candidate.STATUS_REJECTED)
        _ensure_unclaimed(candidate)
        if candidate.decided_by != Candidate.DECIDED_LLM:
            raise CandidateError("Only a decision made by the LLM can be decided again.")
        if not isinstance(candidate.verdict, dict) or "answer" not in candidate.verdict:
            raise CandidateError("This candidate has no usable verdict to decide on; re-judge it instead.")
        status, reason = llm_tasks._judge(task, candidate, candidate.verdict)
        if status != Candidate.STATUS_APPLIED:
            llm_tasks._record(candidate, status, reason, candidate.verdict, Candidate.DECIDED_LLM, timezone.now())
            candidate.save()
            return candidate
        if task.apply_in_transaction:
            return _apply(candidate, decided_by=Candidate.DECIDED_LLM)
    # The two-phase path locks and re-checks the row itself, outside any transaction.
    return _apply(candidate, decided_by=Candidate.DECIDED_LLM)


def _undo_novel(entry):
    """Split the sources a novel merge moved back out, as a new novel under its old id."""
    moved = list(NovelFromSource.objects.filter(pk__in=entry["moved_source_ids"]).select_related("novel"))
    if not moved:
        raise CandidateError("The sources moved by this merge no longer exist.")
    # Later changes may have moved them on: they must all sit on one novel, the holder.
    holder = moved[0].novel
    if any(source.novel_id != holder.pk for source in moved):
        raise CandidateError(
            "The sources moved by this merge are spread over several novels; undo the later changes first."
        )
    if Novel.objects.filter(pk=entry["source_id"]).exists():
        raise CandidateError("The merged-away novel's id is taken.")
    try:
        restored = split_novel(
            holder, moved, new_title=entry["title"], new_slug=entry["slug"],
            novel_id=entry["source_id"],
        )
    except SplitError as exc:
        raise CandidateError(str(exc)) from exc
    Novel.objects.filter(pk=restored.pk).update(
        is_dmca=entry["is_dmca"], added_by_id=entry["added_by"],
    )


def _undo_entry(entry):
    """Reverse one undo entry. Returns the ids it restored (``source_id``, ``target_id``) or None."""
    kind = entry["type"]
    if entry.get("undoable") is False:
        # Copied from the old journals without the ids undo needs.
        raise CandidateError("This change was recorded without the data needed to undo it.")
    if kind == "novel_merge":
        _undo_novel(entry)
    elif kind in ("tag_merge", "tag_rename"):
        return undo_tag_entry(entry)
    elif kind == "author_merge":
        # The restored author keeps the source pk, so the candidate's target_ids stay valid.
        return undo_author_entry(entry)
    elif kind == "tag_r18":
        tag = Tag.objects.filter(pk=entry["tag_id"]).first()
        if tag is None:
            raise CandidateError("The tag no longer exists.")
        Tag.objects.filter(pk=tag.pk).update(is_adult=False)
        refresh_adult_for_tags([tag.pk])
    else:
        raise CandidateError(f"Unknown undo entry type {kind!r}.")


def _write_back_ids(candidate, entry, restored):
    """Name the restored rows by their current pks: a tag undo can recreate a merged-away tag
    under a new id, and find its target under a new id when a later undo recreated it."""
    for field in ("source_id", "target_id"):
        old = entry.get(field)
        new = (restored or {}).get(field)
        if new is not None:
            # Kept on the entry too: blocked_pairs reads the pairs an undone merge rules out.
            entry[f"restored_{field}"] = new
        if old is not None and new is not None and old != new:
            candidate.target_ids = [new if pk == old else pk for pk in candidate.target_ids]


def _undo_all(candidate):
    # Entries undone before (the candidate was undone, then applied again) are not
    # reversed twice: each reversed entry is stamped.
    now = timezone.now()
    entries = [dict(entry) for entry in candidate.undo]
    for entry in reversed(entries):
        if entry.get("undone_at"):
            continue
        _write_back_ids(candidate, entry, _undo_entry(entry))
        entry["undone_at"] = now.isoformat()
        # Saved after each entry: a novel undo runs outside a transaction, so if a later
        # entry fails, a retry must not reverse this one again.
        candidate.undo = entries
        candidate.save(update_fields=["target_ids", "undo", "updated_at"])
    candidate.undo = entries
    candidate.status = Candidate.STATUS_UNDONE
    candidate.undone_at = now
    candidate.save(update_fields=["target_ids", "undo", "status", "undone_at", "updated_at"])


def _ensure_undoable(candidate):
    _ensure_status(candidate, Candidate.STATUS_APPLIED)
    _ensure_unclaimed(candidate)
    pending = [entry for entry in candidate.undo if not entry.get("undone_at")]
    if not pending:
        # e.g. a novel merge copied from before this change: no record of what it moved.
        raise CandidateError("Nothing was recorded for this change, so it cannot be undone.")
    if any(entry.get("undoable") is False for entry in pending):
        # Refused before anything is reversed, so the candidate is never left half undone.
        raise CandidateError("This change was recorded without the data needed to undo it.")


def undo_candidate(candidate):
    """Reverse every change of an applied candidate, newest first."""
    if llm_tasks.REGISTRY[candidate.kind].apply_in_transaction:
        with transaction.atomic():
            candidate = _lock(candidate)
            _ensure_undoable(candidate)
            _undo_all(candidate)
    else:
        # A change that runs outside a transaction is undone outside one too (split_novel
        # opens its own). The claim keeps a second undo, or the runner, off it meanwhile.
        token = timezone.now()
        with transaction.atomic():
            candidate = _lock(candidate)
            _ensure_undoable(candidate)
            Candidate.objects.filter(pk=candidate.pk).update(claimed_at=token)
        try:
            _undo_all(candidate)
        finally:
            Candidate.objects.filter(pk=candidate.pk, claimed_at=token).update(claimed_at=None)
    logger.info("Undid candidate %s (%s)", candidate.pk, candidate.kind)
    return candidate


def rejudge_candidate(candidate):
    """Send a candidate that is not applied back to the LLM queue, with its attempts reset."""
    with transaction.atomic():
        candidate = _lock(candidate)
        _rejudge(candidate)
    return candidate


def _rejudge(candidate):
    _ensure_status(
        candidate, Candidate.STATUS_PENDING, Candidate.STATUS_REVIEW,
        Candidate.STATUS_REJECTED, Candidate.STATUS_ERROR, Candidate.STATUS_UNDONE,
    )
    _ensure_unclaimed(candidate)
    candidate.status = Candidate.STATUS_PENDING
    candidate.attempts = 0
    candidate.not_before = None
    candidate.claimed_at = None
    candidate.decided_by = ""
    candidate.decided_at = None
    candidate.reason = ""
    candidate.save(update_fields=[
        "status", "attempts", "not_before", "claimed_at", "decided_by", "decided_at",
        "reason", "updated_at",
    ])
