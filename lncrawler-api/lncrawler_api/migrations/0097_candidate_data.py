"""Copy the old merge, LLM and undo tables into Candidate and LLMCall (plan section 7).

Runs after the 0096 schema. Idempotent: a candidate whose (kind, signature) already
exists is skipped, and an LLM row already copied (same date, kind, provider and
tokens) is not copied again, so a second run adds nothing. A row that does not map
cleanly goes back to pending (re-judged), or an open row whose target is gone is not
copied, and is counted: the migration does not raise on a row. Only apps.get_model is used, never
app code, so the copy keeps working when the app code changes.
"""

import hashlib
from collections import Counter

from django.db import migrations, transaction

KIND_NOVEL = "novel_merge"
KIND_AUTHOR = "author_merge"
KIND_TAG = "tag_merge"

# Most decided first: when two old rows give the same signature, the best one is kept.
STATUS_RANK = {"applied": 5, "undone": 4, "rejected": 3, "review": 2, "error": 1, "pending": 0}
# Open statuses: a target that is gone drops them, so they are not copied. Decided rows stay as history.
OPEN_STATUSES = ("pending", "review", "error")
AUTHOR_STATUSES = ("pending", "applied", "review", "rejected", "undone", "error")
TAG_STATUSES = ("pending", "applied", "review", "rejected", "undone", "error")
SMALL_INT_MAX = 32767


def _pk_signature(pks):
    # Same value as services/merge_common.sorted_pk_signature.
    return hashlib.sha1(",".join(str(pk) for pk in sorted(pks)).encode()).hexdigest()


def _spec(kind, signature, **fields):
    spec = {
        "kind": kind,
        "signature": signature,
        "target_ids": [],
        "target_names": [],
        "status": "pending",
        "decided_by": "",
        "decided_at": None,
        "certainty": 0.0,
        "signals": {},
        "verdict": None,
        "confidence": None,
        "reason": "",
        "attempts": 0,
    }
    spec.update(fields)
    return spec


def _confidence(verdict):
    """None when there is no verdict; 0.0 when the verdict has no usable confidence."""
    if verdict is None:
        return None
    if isinstance(verdict, dict):
        try:
            return float(verdict.get("confidence"))
        except (TypeError, ValueError):
            pass
    return 0.0


def _usable(verdict, *keys):
    """A verdict that has every key the decision needs. A partial one is kept, not decided on."""
    return isinstance(verdict, dict) and all(key in verdict for key in keys)


# AuthorMergeCandidate.reason values the finder rules wrote ("manual" is an admin merge).
FINDER_RULE_REASONS = {"normalized", "mixed_script", "cross_source"}
AUTHOR_MERGE_RELATIONS = {"bracketed_original", "romanization", "translation", "same_name"}
AUTHOR_NO_RELATIONS = {"different", "other_party"}


def _with_answer(verdict, answer):
    """The old verdict plus the ``answer`` key the runner and re-decide read.

    A verdict that is not a dict (broken JSON) is kept as is: it cannot be decided
    again, only re-judged.
    """
    if not isinstance(verdict, dict) or answer is None:
        return verdict
    return {**verdict, "answer": answer}


def _novel_answer(verdict):
    if not isinstance(verdict, dict) or "same" not in verdict:
        return None
    return "yes" if verdict.get("same") is True else "no"


def _author_answer(verdict):
    relation = verdict.get("relation") if isinstance(verdict, dict) else None
    if relation in AUTHOR_MERGE_RELATIONS:
        return "yes"
    if relation in AUTHOR_NO_RELATIONS:
        return "no"
    return "unsure" if relation else None


def _tag_answer(verdict):
    sets = verdict.get("sets") if isinstance(verdict, dict) else None
    if not isinstance(sets, list):
        return None
    return "yes" if sets else "no"


def _set_confidence(response):
    """Lowest confidence of the proposed sets. No set: None (the implicit "no merge")."""
    if response is None:
        return None
    sets = response.get("sets") if isinstance(response, dict) else None
    if not isinstance(sets, list):
        return 0.0
    if not sets:
        return None
    return min((_confidence(item) or 0.0) for item in sets)


def _same_status(old, allowed, kind, stats):
    if old in allowed:
        return old
    stats[f"{kind}: unknown status {old!r} -> pending"] += 1
    return "pending"


def _drop_if_gone(spec, gone, stats):
    """Flag an open row whose target is gone as dropped: it is not copied."""
    if gone and spec["status"] in OPEN_STATUSES:
        stats[f"{spec['kind']}: dropped: target gone"] += 1
        spec["dropped"] = True
    return spec


def _novel_status(row, verdict, stats):
    """(status, decided_by, decided_at) of an old MergeCandidate."""
    if row.status == "pending":
        if row.llm_checked_at is None:
            return "pending", "", None
        if not _usable(verdict, "same", "confidence"):
            # Judged, but the verdict is broken: back to pending so it is judged again.
            stats["novel_merge: unusable verdict -> pending (re-judged)"] += 1
            return "pending", "", None
        return "review", "", None
    if row.status == "merged":
        return "applied", ("llm" if row.decision == "auto" else "human"), row.merged_at
    if row.status == "rejected":
        return "rejected", "human", None
    if row.status == "skipped":
        llm = isinstance(verdict, dict) and bool(verdict) and not verdict.get("same")
        return "rejected", ("llm" if llm else "system"), None
    stats[f"novel_merge: unknown status {row.status!r} -> pending"] += 1
    return "pending", "", None


def _convert_novel(row, stats):
    a = row.novel_a_id if row.novel_a_id is not None else row.novel_a_id_snapshot
    b = row.novel_b_id if row.novel_b_id is not None else row.novel_b_id_snapshot
    if a is None or b is None:
        # Neither the novel nor its snapshot: kept as history, never deduplicated.
        signature = f"legacy:{row.pk}"
    else:
        signature = _pk_signature([a, b])
    verdict = row.llm_verdict
    status, decided_by, decided_at = _novel_status(row, verdict, stats)
    spec = _spec(
        KIND_NOVEL,
        signature,
        target_ids=[str(pk) for pk in (a, b) if pk is not None],
        target_names=[row.title_a, row.title_b],
        status=status,
        decided_by=decided_by,
        decided_at=decided_at,
        certainty=row.certainty,
        signals=row.signals,
        verdict=_with_answer(verdict, _novel_answer(verdict)),
        confidence=_confidence(verdict),
        reason=row.llm_reason,
    )
    return _drop_if_gone(spec, row.novel_a_id is None or row.novel_b_id is None, stats)


def _convert_author(row, known, stats):
    status = _same_status(row.status, AUTHOR_STATUSES, KIND_AUTHOR, stats)
    response = row.llm_response
    if status in ("applied", "rejected") and response:
        decided_by = "llm"
    elif status == "applied" and row.reason in FINDER_RULE_REASONS:
        # Merged by a finder rule with no LLM call (rules removed by this change).
        decided_by = "system"
    elif status in ("applied", "rejected", "undone"):
        # No LLM answer on record: a human decided it.
        decided_by = "human"
    else:
        decided_by = ""
    ids = list(row.author_ids or [])
    spec = _spec(
        KIND_AUTHOR,
        row.signature,
        target_ids=ids,
        target_names=list(row.author_names or []),
        status=status,
        decided_by=decided_by,
        decided_at=row.decided_at,
        signals=row.signals,
        verdict=_with_answer(response, _author_answer(response)),
        confidence=_confidence(response),
        reason=row.reason,
    )
    return _drop_if_gone(spec, any(pk not in known["authors"] for pk in ids), stats)


def _convert_tag(row, known, stats):
    response = row.llm_response
    if row.status == "no_merge":
        status, decided_by = "rejected", ("llm" if response else "system")
    else:
        status = _same_status(row.status, TAG_STATUSES, KIND_TAG, stats)
        if status in ("applied", "rejected"):
            decided_by = "llm" if response else "human"
        elif status == "undone":
            decided_by = "human"
        else:
            decided_by = ""
    ids = list(row.tag_ids or [])
    spec = _spec(
        KIND_TAG,
        row.signature,
        target_ids=ids,
        target_names=list(row.tag_names or []),
        status=status,
        decided_by=decided_by,
        decided_at=row.judged_at,
        signals=row.signals,
        verdict=_with_answer(response, _tag_answer(response)),
        confidence=_set_confidence(response),
        reason=row.error,
        attempts=min(row.requeue_count, SMALL_INT_MAX),
    )
    return _drop_if_gone(spec, any(pk not in known["tags"] for pk in ids), stats)


# Old novel status -> (status, decided_by, decided_at) when the row could not be converted.
FALLBACK_NOVEL_STATUSES = {
    "pending": ("pending", "", None),
    "merged": ("applied", "human", None),
    "rejected": ("rejected", "human", None),
    "skipped": ("rejected", "system", None),
}


def _fallback(kind, row, stats):
    """The row raised while converting: pending again, or closed when a novel is gone.

    An open row whose novel is gone is dropped, not copied (§12); a decided one is kept as history.
    """
    if kind == KIND_NOVEL:
        # The decision is kept as the row had it (a human rejection must not come back
        # as pending); only the verdict, which may be what broke, is left out.
        status, decided_by, decided_at = FALLBACK_NOVEL_STATUSES.get(row.status, ("pending", "", None))
        if status == "applied":
            decided_by = "llm" if getattr(row, "decision", "") == "auto" else "human"
            decided_at = getattr(row, "merged_at", None)
        a = row.novel_a_id if row.novel_a_id is not None else getattr(row, "novel_a_id_snapshot", None)
        b = row.novel_b_id if row.novel_b_id is not None else getattr(row, "novel_b_id_snapshot", None)
        gone = row.novel_a_id is None or row.novel_b_id is None
        if gone and status in OPEN_STATUSES:
            stats[f"{kind}: dropped: target gone"] += 1
            return _spec(kind, f"legacy:{row.pk}", dropped=True)
        pair = [pk for pk in (a, b) if pk is not None]
        signature = _pk_signature(pair) if len(pair) == 2 else f"legacy:{row.pk}"
        return _spec(
            kind, signature, target_ids=[str(pk) for pk in pair],
            status=status, decided_by=decided_by, decided_at=decided_at,
        )
    return _spec(kind, row.signature)


def _iso(value):
    return value.isoformat() if value is not None else None


def _author_entry(merge):
    entry = {
        "type": "author_merge",
        "legacy_id": merge.pk,
        "source_name": merge.source_name,
        "source_id": merge.source_id,
        "target_id": merge.target_id,
        "target_name": merge.target_name,
        "source_ids": list(merge.source_ids or []),
        "added_source_ids": list(merge.added_source_ids or []),
        "moved_alias_ids": list(merge.moved_alias_ids or []),
        "alias_created": merge.alias_created,
        "created_at": _iso(merge.created_at),
        "undone_at": _iso(merge.undone_at),
    }
    if merge.source_id is None or merge.target_id is None:
        entry["undoable"] = False
    return entry


def _tag_entry(merge):
    entry = {
        "type": "tag_rename" if merge.kind == "rename" else "tag_merge",
        "legacy_id": merge.pk,
        "source_name": merge.source_name,
        "target_id": merge.target_id,
        "target_name": merge.target_name,
        "all_source_ids": list(merge.all_source_ids or []),
        "added_source_ids": list(merge.added_source_ids or []),
        "moved_alias_ids": list(merge.moved_alias_ids or []),
        "renamed_from": merge.renamed_from,
        "source_was_adult": merge.source_was_adult,
        "target_was_adult": merge.target_was_adult,
        "created_at": _iso(merge.created_at),
        "undone_at": _iso(merge.undone_at),
    }
    # Merges recorded before the R18 flags existed are still undone, as before, but
    # their R18 flags are left as they are (undo_tag_entry skips None flags).
    if merge.kind == "merge" and (merge.source_was_adult is None or merge.target_was_adult is None):
        entry["adult_flags_unknown"] = True
    if merge.target_id is None:
        entry["undoable"] = False
    return entry


def _write(stats, label, make):
    """Run ``make()`` in a savepoint: a row that fails is counted and skipped, the migration goes on."""
    try:
        with transaction.atomic():
            return make()
    except Exception:
        stats[f"{label}: row could not be copied, skipped"] += 1
        return None


def _note_undone(state, pk, undone_at):
    """Track, per candidate, whether every journal row is undone and the latest undo time."""
    all_done, latest = state.get(pk, (True, None))
    if undone_at is None:
        all_done = False
    elif latest is None or undone_at > latest:
        latest = undone_at
    state[pk] = (all_done, latest)


def _fold_journal(Candidate, kind, mapped_sig, manual_sig, manual, legacy_id, entry, undone_at,
                  pk_by_key, undone, stats):
    pk = pk_by_key.get((kind, mapped_sig))
    if pk is not None:
        cand = Candidate.objects.get(pk=pk)
    else:
        # A manual merge, or its candidate was deleted: its own applied/human candidate.
        cand = Candidate.objects.filter(kind=kind, signature=manual_sig).first()
        if cand is None:
            stats[f"{kind}: journal without candidate -> applied/human"] += 1
            cand = Candidate.objects.create(
                kind=kind, signature=manual_sig, status="applied", decided_by="human", **manual
            )
    _note_undone(undone, cand.pk, undone_at)
    if any(old.get("type") == entry["type"] and old.get("legacy_id") == legacy_id for old in cand.undo):
        # Copied by an earlier run.
        return cand.pk
    cand.undo = [*cand.undo, entry]
    cand.save(update_fields=["undo", "updated_at"])
    return cand.pk


def _journal_entry(build, merge, entry_type, stats):
    try:
        return build(merge)
    except Exception:
        stats[f"{entry_type} journal: unexpected error -> undoable false"] += 1
        return {"type": entry_type, "legacy_id": merge.pk, "undoable": False}


def _copy_journals(apps, pk_by_key, sig_by_old, stats):
    AuthorMerge = apps.get_model("lncrawler_api", "AuthorMerge")
    TagMerge = apps.get_model("lncrawler_api", "TagMerge")
    Candidate = apps.get_model("lncrawler_api", "Candidate")
    undone = {}

    for merge in AuthorMerge.objects.order_by("created_at", "pk"):
        entry = _journal_entry(_author_entry, merge, "author_merge", stats)
        manual_sig = f"manual:author:{merge.pk}"
        manual = {
            "target_ids": [pk for pk in (merge.target_id, merge.source_id) if pk is not None],
            "target_names": [name for name in (merge.target_name, merge.source_name) if name],
            "decided_at": merge.created_at,
        }
        _write(stats, "author journal", lambda merge=merge, entry=entry, manual=manual, manual_sig=manual_sig: _fold_journal(
            Candidate, KIND_AUTHOR, sig_by_old.get((KIND_AUTHOR, str(merge.candidate_id))),
            manual_sig, manual, merge.pk, entry, merge.undone_at, pk_by_key, undone, stats,
        ))

    for merge in TagMerge.objects.order_by("created_at", "pk"):
        entry = _journal_entry(_tag_entry, merge, "tag_merge", stats)
        manual_sig = f"manual:tag:{merge.pk}"
        manual = {
            "target_ids": list(dict.fromkeys(
                pk for pk in [merge.target_id, *(merge.all_source_ids or [])] if pk is not None
            )),
            "target_names": [name for name in (merge.target_name, merge.source_name, merge.renamed_from) if name],
            "decided_at": merge.created_at,
        }
        _write(stats, "tag journal", lambda merge=merge, entry=entry, manual=manual, manual_sig=manual_sig: _fold_journal(
            Candidate, KIND_TAG, sig_by_old.get((KIND_TAG, str(merge.cluster_id))),
            manual_sig, manual, merge.pk, entry, merge.undone_at, pk_by_key, undone, stats,
        ))

    for pk, (all_done, latest) in undone.items():
        if all_done and latest is not None:
            Candidate.objects.filter(pk=pk, undone_at__isnull=True).update(undone_at=latest)


def _copy_no_merges(apps, stats):
    TagNoMerge = apps.get_model("lncrawler_api", "TagNoMerge")
    Candidate = apps.get_model("lncrawler_api", "Candidate")
    Tag = apps.get_model("lncrawler_api", "Tag")
    tag_names = dict(Tag.objects.values_list("pk", "name"))
    # Every pair is copied, even one inside a refused cluster: a copied cluster only blocks
    # the sets of its LLM answer, and a copied undone one has no merged ids to block.
    existing = set(Candidate.objects.filter(kind=KIND_TAG).values_list("signature", flat=True))

    for row in TagNoMerge.objects.order_by("created_at", "pk"):
        a, b = sorted((row.tag_a_id, row.tag_b_id))
        if a not in tag_names or b not in tag_names:
            stats["tag no-merge: a tag is gone -> dropped"] += 1
            continue
        signature = f"nomerge:{a}:{b}"
        if signature in existing:
            continue
        _write(stats, "tag no-merge", lambda a=a, b=b, signature=signature, row=row: Candidate.objects.create(
            kind=KIND_TAG,
            signature=signature,
            target_ids=[a, b],
            target_names=[tag_names[a], tag_names[b]],
            status="rejected",
            decided_by="human",
            decided_at=row.created_at,
        ))


def _mapped_ids(task, target_ids, pk_by_key, sig_by_old):
    """New candidate pks for the old targets of one LLM request (unmapped targets are dropped)."""
    ids = []
    for old in target_ids or []:
        pk = pk_by_key.get((task, sig_by_old.get((task, str(old)))))
        if pk is not None and pk not in ids:
            ids.append(pk)
    return ids


def _copy_llm(apps, pk_by_key, sig_by_old, stats):
    LLMCall = apps.get_model("lncrawler_api", "LLMCall")
    LLMRequest = apps.get_model("lncrawler_api", "LLMRequest")
    LLMUsage = apps.get_model("lncrawler_api", "LLMUsage")
    Candidate = apps.get_model("lncrawler_api", "Candidate")
    # Snapshot taken before this run: a row copied by this run is not matched against itself.
    existing = {
        (created_at, kind, provider, tokens): pk
        for pk, created_at, kind, provider, tokens in LLMCall.objects.values_list(
            "pk", "created_at", "kind", "provider", "tokens"
        )
    }
    calls_of = {}  # candidate pk -> the LLM call pks that covered it

    # Budget: LLMUsage is the one row per provider reply that carries the tokens.
    for usage in LLMUsage.objects.order_by("created_at", "pk"):
        key = (usage.created_at, usage.purpose, usage.provider, usage.tokens)
        if key in existing:
            stats["llm usage: already copied"] += 1
            continue
        _write(stats, "llm usage", lambda usage=usage: LLMCall.objects.create(
            kind=usage.purpose,
            provider=usage.provider,
            tokens=usage.tokens,
            created_at=usage.created_at,
        ))

    # Log: done/failed requests keep the raw reply and error. Their tokens stay at 0 because
    # the LLMUsage row of the same reply already counts them; counting both would double the budget.
    for req in LLMRequest.objects.order_by("created_at", "pk"):
        if req.status not in ("done", "failed"):
            # Pending/running: their candidates are still pending and get judged again.
            stats["llm request pending/running: not copied"] += 1
            continue
        when = req.finished_at or req.created_at
        key = (when, req.task, "(request log)", 0)
        ids = _mapped_ids(req.task, req.target_ids, pk_by_key, sig_by_old)
        if key in existing:
            call_pk = existing[key]
            stats["llm request: already copied"] += 1
        else:
            call_pk = _write(stats, "llm request", lambda req=req, when=when, ids=ids: LLMCall.objects.create(
                kind=req.task,
                # llm_service.REQUEST_LOG_PROVIDER: the budget skips these rows, so a call is
                # counted once (by its usage row) in requests as well as in tokens.
                provider="(request log)",
                model=req.model,
                prompt_version=req.prompt_version,
                tokens=0,
                raw_response=req.raw_response,
                error=req.error,
                candidate_ids=ids,
                created_at=when,
            ).pk)
        if call_pk is None:
            continue
        for pk in ids:
            calls_of.setdefault(pk, set()).add(call_pk)

    # llm_call is set only when exactly one call answered the candidate.
    for pk, call_pks in calls_of.items():
        if len(call_pks) == 1:
            Candidate.objects.filter(pk=pk, llm_call__isnull=True).update(llm_call_id=next(iter(call_pks)))
        else:
            stats["candidate: answered by several LLM calls, llm_call left empty"] += 1


def copy_candidates(apps, schema_editor):
    stats = Counter()
    Candidate = apps.get_model("lncrawler_api", "Candidate")
    MergeCandidate = apps.get_model("lncrawler_api", "MergeCandidate")
    AuthorMergeCandidate = apps.get_model("lncrawler_api", "AuthorMergeCandidate")
    TagCluster = apps.get_model("lncrawler_api", "TagCluster")
    Author = apps.get_model("lncrawler_api", "Author")
    Tag = apps.get_model("lncrawler_api", "Tag")

    known = {
        "authors": set(Author.objects.values_list("pk", flat=True)),
        "tags": set(Tag.objects.values_list("pk", flat=True)),
    }
    sources = [
        (KIND_NOVEL, MergeCandidate.objects.order_by("created_at", "pk"),
         lambda row: _convert_novel(row, stats)),
        (KIND_AUTHOR, AuthorMergeCandidate.objects.order_by("created_at", "pk"),
         lambda row: _convert_author(row, known, stats)),
        (KIND_TAG, TagCluster.objects.order_by("created_at", "pk"),
         lambda row: _convert_tag(row, known, stats)),
    ]

    # One spec per (kind, signature), the most decided one. sig_by_old maps every old row
    # (dropped ones too) to its signature, for the journals and the LLM history.
    best = {}
    sig_by_old = {}
    for kind, queryset, convert in sources:
        for row in queryset:
            try:
                spec = convert(row)
            except Exception:
                stats[f"{kind}: unexpected error -> fallback"] += 1
                spec = _fallback(kind, row, stats)
            sig_by_old[(kind, str(row.pk))] = spec["signature"]
            if spec.pop("dropped", False):
                continue
            key = (kind, spec["signature"])
            if key in best:
                stats[f"{kind}: duplicate signature dropped"] += 1
                if STATUS_RANK.get(best[key]["status"], 0) >= STATUS_RANK.get(spec["status"], 0):
                    continue
            best[key] = spec

    existing = set(Candidate.objects.values_list("kind", "signature"))
    for key, spec in best.items():
        if key in existing:
            stats[f"{key[0]}: already copied"] += 1
            continue
        _write(stats, key[0], lambda spec=spec: Candidate.objects.create(**spec))

    pk_by_key = {
        (kind, signature): pk
        for pk, kind, signature in Candidate.objects.values_list("pk", "kind", "signature")
    }
    _copy_journals(apps, pk_by_key, sig_by_old, stats)
    _copy_no_merges(apps, stats)
    _copy_llm(apps, pk_by_key, sig_by_old, stats)

    print("\nlncrawler_api 0097: candidates copied from the old tables")
    for label in sorted(stats):
        print(f"  {label}: {stats[label]}")
    counts = Counter(Candidate.objects.values_list("kind", "status"))
    for (kind, status), count in sorted(counts.items()):
        print(f"  {kind} {status}: {count}")
    print(f"  llm calls: {apps.get_model('lncrawler_api', 'LLMCall').objects.count()}")


class Migration(migrations.Migration):

    dependencies = [
        ('lncrawler_api', '0096_candidate_llmcall'),
    ]

    operations = [
        migrations.RunPython(copy_candidates, migrations.RunPython.noop),
    ]
