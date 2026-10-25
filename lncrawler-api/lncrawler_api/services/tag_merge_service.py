"""Tag vocabulary cleanup: propose groups of possibly-duplicate tags, then judge them.

Stage 1 (``find_tag_merge_candidates``) proposes groups of tags that might be the
same concept, from three signals:

- embedding similarity of the tag names (``embedding_edges``),
- co-occurrence across different sources of the same novel (``cooccurrence_edges``),
- trigram similarity of the normalized keys (``trigram_edges``).

Groups are stored as ``tag_merge`` candidates. Stage 2
(``TagMergeTask`` in services/llm_tasks.py) asks an LLM which members are strictly interchangeable,
and ``apply_sets`` merges them, or the candidate is held for review when a safeguard trips.

Every pure function here takes plain data so it can be unit tested without the
network. Helpers that touch the database are kept small and explicit.
"""

import json
import logging
import re
import time
from collections import defaultdict
from itertools import combinations

import numpy as np
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Count, Q
from scipy import sparse

from . import embedding_service, llm_service
from .candidate_blocks import blocked_pairs, pair_key
from .merge_common import sorted_pk_signature
from .merge_service import MergeError, apply_rename, fold_tag
from ..db_locks import lock_pks
from ..models import Candidate, Tag

logger = logging.getLogger("lncrawler_api.merge")

# Rows of the embedding similarity matrix computed at once (bounds memory).
EMBED_CHUNK = 256
# Tag columns processed per co-occurrence block (bounds memory).
COOC_BLOCK = 2000
# Seconds to wait after a rate-limit when the provider gives no Retry-After.
DEFAULT_RETRY_SECONDS = 10
EMBED_MAX_RETRIES = 3

SYSTEM_PROMPT = """You merge duplicate tags of a web/light-novel catalogue. Tags come from many websites and languages (English, French, Spanish, Portuguese, Russian, Indonesian, Vietnamese, Chinese, Japanese, Korean, romanizations...) and contain typos.
Each numbered group holds tags that an automatic system flagged as possibly similar. Most of them are NOT duplicates, only related; returning no set for a group is normal.

For each group:
1. "glosses": the literal English meaning of every tag that is not plain English, as "t2=space travel; t5=ninja" (skip English tags). Use the meaning the word has as a genre tag on novel sites, not only the dictionary one: Chinese 都市 is the "Urban" genre (stories in a modern city), not "City".
2. "sets": the tags that are strictly interchangeable: replacing one by another on any novel would never add, remove or change information. Merge only when tags are:
- the same concept in different languages, judged by their glosses, not by spelling (Reincarnation = 转生 = Reencarnación);
- spelling, typo, abbreviation, romanization, punctuation or word-order variants (Sci-fi = Science Fiction, Post Apocalyptic = Post-apocalyptic, Rom-com = Romantic Comedy);
- established synonyms readers use for exactly the same concept (Kingdom Building = Nation Building).
Put every tag of the group that names that exact concept in the same set.
One set holds one concept. When a group holds duplicates of two distinct concepts, give two sets, never one mixed set: Adventure = Aventura = 冒険 and Adventurers = 冒険者 = Авантюристы are two sets. A tag that has no duplicate in the group stays out of every set.

NEVER merge:
- a broader and a narrower tag, even across languages (Romance / Slow Romance, Mystery / Detective, Monsters / Monster Girls, 恋爱 (romance) / 纯爱 (pure love));
- related but distinct concepts (Vampires / Werewolves, Cooking / Restaurant, Necromancy / Undead, Space / Space Opera);
- different roles, audiences, genders or degrees (Older Love Interest / Younger Love Interest, Yaoi / Yuri, Shoujo / Josei, Slow Pace / Fast Pace);
- tags that only share a word (Time Travel / Time Travel Romance, Pirates / Pirate King) or a theme (Ninjas / Samurai, Ghosts / Exorcism);
- false friends: a tag whose genre meaning differs from its literal look (都市 / City Building);
- tags that merely tend to appear on the same novels;
- tags of different kinds (a person or role, a place, a genre, an activity, a trope or feature, a format or status marker), even when they share a word or appear together: Police / Detectives, Acting / Action, Adventurers (people who adventure) / Adventure (the genre), Supernatural / Science Fiction, Supernatural / Surrealism;
- different genres, even when one looks like the other: Danmei (BL genre) / Romance;
- metadata labels: word or chapter counts, "Completed", "Ongoing", ratings, award or contest names, site-specific labels, numbers and dates.
If you are not sure, do not merge.

For each set give:
- "canonical": the name English-speaking readers commonly use, in Title Case. Prefer an existing member's spelling when one is already correct English.
- "confidence": 0..1, how sure you are that ALL members are interchangeable. Use 0.95 or more only when every member clearly names the same concept.
Reply with one compact JSON object:
{"groups":[{"group":1,"glosses":"t2=reincarnation","sets":[{"members":["t1","t2"],"canonical":"Reincarnation","confidence":0.97}]},{"group":2,"glosses":"t2=adventure; t3=adventure; t5=adventurers; t6=adventurers","sets":[{"members":["t1","t2","t3"],"canonical":"Adventure","confidence":0.97},{"members":["t4","t5","t6"],"canonical":"Adventurers","confidence":0.96}]}]}"""

VERIFY_PROMPT = """You check sets of tags of a web/light-novel catalogue that another model proposed as duplicates. Each numbered set has a canonical name and its members, with the literal English meaning of each member when it is not English.

For each member, answer one question: is it the exact same concept as the canonical name, as a tag on novel sites, whatever its kind (genre, person or role, place, trope)? Keep a member only when the answer is clearly yes. A broader, narrower, related or different-kind tag is not the same concept, and neither is a tag that only shares a word with the canonical name.
You may only remove members. Never add one, and never move one to another set.
Reply with one compact JSON object giving, for each set id, the labels of the members that stay:
{"sets":[{"set":"s1","keep":["t1","t2"]}]}"""


# --------------------------------------------------------------- stage 1: signals
def load_embeddings():
    """Return ``(tag_ids, matrix)`` for every tag embedded by the current model."""
    rows = list(
        Tag.objects.filter(embedding__isnull=False, embedding_model=settings.EMBED_MODEL)
        .order_by("pk")
        .values_list("pk", "embedding")
    )
    if not rows:
        return [], np.zeros((0, 0), dtype=np.float32)
    width = len(bytes(rows[0][1])) // 4
    kept = [(pk, bytes(blob)) for pk, blob in rows if len(blob) == width * 4]
    ids = [pk for pk, _ in kept]
    matrix = np.vstack([np.frombuffer(blob, dtype=np.float32) for _, blob in kept])
    return ids, matrix


def embed_missing(batch_size=None, sleep=time.sleep):
    """Embed every tag whose vector is missing or came from another model.

    Returns the number of tags embedded. A rate-limit is retried a few times
    with the provider's Retry-After; after that embedding stops for this run and
    the rest of the candidate pipeline continues on the vectors already stored.
    """
    if not embedding_service.is_configured():
        logger.warning("Tag embeddings skipped: EMBED_API_KEY is empty")
        return 0

    batch_size = batch_size or settings.EMBED_BATCH
    model = settings.EMBED_MODEL
    pending = list(
        Tag.objects.filter(Q(embedding__isnull=True) | ~Q(embedding_model=model))
        .order_by("pk")
        .only("pk", "name")
    )

    done = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        vectors = None
        for attempt in range(EMBED_MAX_RETRIES + 1):
            try:
                vectors = embedding_service.embed([tag.name for tag in batch])
                break
            except llm_service.RateLimited as exc:
                if attempt == EMBED_MAX_RETRIES:
                    logger.warning("Tag embedding rate limited; stopping for this run")
                    return done
                sleep(_retry_seconds(exc.retry_after))
            except llm_service.LLMError as exc:
                logger.warning("Tag embedding failed: %s", exc)
                return done

        for tag, vector in zip(batch, vectors):
            tag.embedding = np.asarray(vector, dtype=np.float32).tobytes()
            tag.embedding_model = model
        Tag.objects.bulk_update(batch, ["embedding", "embedding_model"])
        done += len(batch)
    return done


def _retry_seconds(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return DEFAULT_RETRY_SECONDS


def embedding_edges(ids, matrix, top_k, min_cos):
    """Nearest neighbours by cosine similarity. Returns ``{(a, b): cos}`` with a < b."""
    ids = list(ids)
    n = len(ids)
    if n < 2 or top_k <= 0:
        return {}

    X = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    X = X / np.where(norms == 0, 1.0, norms)

    k = min(top_k, n - 1)
    edges = {}
    for start in range(0, n, EMBED_CHUNK):
        stop = min(start + EMBED_CHUNK, n)
        sims = X[start:stop] @ X.T
        rows = np.arange(stop - start)
        sims[rows, start + rows] = -np.inf  # a tag is not its own neighbour
        top = np.argpartition(-sims, k - 1, axis=1)[:, :k]
        for r in range(stop - start):
            a = ids[start + r]
            for j in top[r]:
                cos = float(sims[r, j])
                if cos < min_cos:
                    continue
                b = ids[j]
                edges[(a, b) if a < b else (b, a)] = cos
    return edges


def cooccurrence_edges(rows, min_novels, min_ratio, top_k, block=COOC_BLOCK):
    """Tags that appear on the same novel through different sources.

    ``rows`` are ``(novelfromsource_id, tag_id, novel_id)`` triples. A pair is
    kept when the two tags share at least ``min_novels`` novels, their shared
    count is at least ``min_ratio`` of the rarer tag's novels, and no single
    source carries both (synonyms are not tagged together on one source, while
    related tags are). Each tag keeps at most ``top_k`` edges. Returns
    ``{(a, b): ratio}`` with a < b.
    """
    source_index, novel_index, tag_index, tag_ids = {}, {}, {}, []
    src, tag, nov = [], [], []
    for source_id, tag_id, novel_id in rows:
        src.append(source_index.setdefault(source_id, len(source_index)))
        if tag_id not in tag_index:
            tag_index[tag_id] = len(tag_ids)
            tag_ids.append(tag_id)
        tag.append(tag_index[tag_id])
        nov.append(novel_index.setdefault(novel_id, len(novel_index)))
    if not src:
        return {}

    ones = np.ones(len(src), dtype=np.float32)
    # M: source x tag membership; P: novel x source membership (both binary).
    M = sparse.csr_matrix((ones, (src, tag)), shape=(len(source_index), len(tag_ids)))
    M.data[:] = 1
    P = sparse.csr_matrix((ones, (nov, src)), shape=(len(novel_index), len(source_index)))
    P.data[:] = 1
    # T: novel x tag, binary. A novel carries a tag if any of its sources does.
    T = (P @ M).tocsr()
    T.data[:] = 1
    T = T.tocsc()
    TT = T.T.tocsr()
    df = np.asarray(T.sum(axis=0)).ravel()

    edges = {}
    for start in range(0, len(tag_ids), block):
        stop = min(start + block, len(tag_ids))
        C = (TT @ T[:, start:stop]).tocsc()
        S = (M.T @ M[:, start:stop]).tocsr()
        # Drop pairs that share a source entry (synonyms are never tagged together
        # on one entry). Both matrices are tags x block, so the shapes line up.
        C = C - C.multiply(S > 0)
        C.eliminate_zeros()
        C = C.tocoo()
        for i, j, count in zip(C.row.tolist(), C.col.tolist(), C.data.tolist()):
            b = start + j
            if i == b or count < min_novels:
                continue
            ratio = float(count / min(df[i], df[b]))
            if ratio < min_ratio:
                continue
            a_id, b_id = tag_ids[i], tag_ids[b]
            edges[(a_id, b_id) if a_id < b_id else (b_id, a_id)] = ratio

    kept, taken = {}, defaultdict(int)
    for pair, ratio in sorted(edges.items(), key=lambda item: (-item[1], item[0])):
        a, b = pair
        if taken[a] >= top_k or taken[b] >= top_k:
            continue
        taken[a] += 1
        taken[b] += 1
        kept[pair] = ratio
    return kept


def trigram_edges(threshold):
    """Tag pairs whose normalized keys are similar per pg_trgm. Returns ``{(a, b): sim}``."""
    table = connection.ops.quote_name(Tag._meta.db_table)
    sql = (
        "SELECT a.id, b.id, similarity(a.normalized, b.normalized) "
        f"FROM {table} a JOIN {table} b "
        "ON a.normalized % b.normalized AND a.id < b.id"
    )
    with transaction.atomic(), connection.cursor() as cursor:
        # set_config(..., true) is SET LOCAL that accepts a bound parameter.
        cursor.execute(
            "SELECT set_config('pg_trgm.similarity_threshold', %s, true)", [str(threshold)]
        )
        cursor.execute(sql)
        rows = cursor.fetchall()
    return {(a, b): float(sim) for a, b, sim in rows if sim >= threshold}


def merge_signal_edges(**signals):
    """Combine per-signal ``{pair: score}`` maps into ``{pair: {signal: score}}``."""
    edges = {}
    for name, pairs in signals.items():
        for pair, score in pairs.items():
            edges.setdefault(pair, {})[name] = float(score)
    return edges


# ------------------------------------------------------------- stage 1: clustering
def build_clusters(edges, max_size, blocked=()):
    """Group tags into clusters, strongest pairs first, capped at ``max_size``.

    ``edges`` maps ``(a, b)`` to ``{signal: score}``; a pair's rank is its best
    signal. Pairs in ``blocked`` (``candidate_blocks.pair_key`` pairs) are dropped
    first. Returns ``[(sorted_member_ids, {"a-b": signals})]`` for groups of two or more.
    """
    blocked = set(blocked)
    usable = {}
    for pair, signals in edges.items():
        a, b = sorted(pair)
        if pair_key(a, b) in blocked or not signals:
            continue
        usable[(a, b)] = signals
    ranked = sorted(usable.items(), key=lambda item: (-max(item[1].values()), item[0]))

    parent, size = {}, {}

    def find(x):
        parent.setdefault(x, x)
        size.setdefault(x, 1)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (a, b), _signals in ranked:
        ra, rb = find(a), find(b)
        if ra == rb or size[ra] + size[rb] > max_size:
            continue
        if size[ra] < size[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        size[ra] += size[rb]

    groups = defaultdict(list)
    for node in list(parent):
        groups[find(node)].append(node)

    clusters = []
    for members in groups.values():
        if len(members) < 2:
            continue
        member_set = set(members)
        signals = {
            f"{a}-{b}": dict(sig)
            for (a, b), sig in usable.items()
            if a in member_set and b in member_set
        }
        clusters.append((sorted(members), signals))
    clusters.sort(key=lambda item: item[0])
    return clusters


def store_clusters(clusters):
    """Create a pending ``tag_merge`` candidate per new group. Returns how many were created.

    A group that already has a candidate, whatever its status, is left alone.
    """
    all_ids = {pk for ids, _ in clusters for pk in ids}
    names = dict(Tag.objects.filter(pk__in=all_ids).values_list("pk", "name"))
    created = 0
    for ids, signals in clusters:
        signature = sorted_pk_signature(ids)
        _row, made = Candidate.objects.get_or_create(
            kind=Candidate.KIND_TAG_MERGE,
            signature=signature,
            defaults={"target_ids": ids, "target_names": [names[pk] for pk in ids], "signals": signals},
        )
        created += made
    return created


# ---------------------------------------------------------------- stage 2: judging
def tag_usage(tag_ids):
    """Map each tag id to the number of sources carrying it (its usage count)."""
    return dict(
        Tag.objects.filter(pk__in=list(tag_ids))
        .annotate(n=Count("novels"))
        .values_list("pk", "n")
    )


def build_judge_messages(groups):
    """Chat messages asking the model to judge ``groups``.

    ``groups`` is a list of groups; each group is a list of ``(label, name,
    usage)`` tuples, with labels local to the group (t1, t2, ...).
    """
    lines = []
    for number, members in enumerate(groups, 1):
        lines.append(f"Group {number}:")
        for label, name, usage in members:
            clean = " ".join(str(name).split())[:100]
            lines.append(f"{label}. {clean} ({usage} novels)")
        lines.append("")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(lines).rstrip()},
    ]


def parse_judge_response(data, label_maps):
    """Validate the model's answer against the labels that were sent.

    ``label_maps[g]`` maps the labels of group ``g`` to tag ids. Returns one list
    of sets per group, each ``{"members": [tag ids], "canonical", "confidence"}``,
    the confidence being ``None`` when the model gave none usable. Raises
    ``LLMParseError`` when the answer has no ``groups`` list at all; every other
    problem only drops the offending label or set.
    """
    raw_groups = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(raw_groups, list):
        raise llm_service.LLMParseError("LLM answer has no 'groups' list")

    results = [[] for _ in label_maps]
    for item in raw_groups:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("group")) - 1
        except (TypeError, ValueError):
            continue
        if not 0 <= index < len(label_maps):
            continue

        labels = label_maps[index]
        raw_sets = item.get("sets")
        if not isinstance(raw_sets, list):
            continue
        used = set()
        for raw_set in raw_sets:
            if not isinstance(raw_set, dict):
                continue
            raw_members = raw_set.get("members")
            if not isinstance(raw_members, list):
                continue
            members = []
            for label in raw_members:
                if (
                    isinstance(label, str)
                    and label in labels
                    and label not in used
                    and label not in members
                ):
                    members.append(label)
            if len(members) < 2:
                continue
            canonical = raw_set.get("canonical")
            if not isinstance(canonical, str):
                continue
            canonical = " ".join(canonical.split())
            if not canonical or len(canonical) > 100:
                continue
            used.update(members)
            results[index].append({
                "members": [labels[label] for label in members],
                "canonical": canonical,
                "confidence": llm_service.parse_confidence(raw_set.get("confidence"), default=None),
            })
    return results


def parse_glosses(text):
    """Map each label to its English gloss, from ``"t2=space travel; t5=ninja"``."""
    glosses = {}
    for part in re.split(r"[;|]", text or ""):
        label, sep, gloss = part.partition("=")
        label, gloss = label.strip(), " ".join(gloss.split())
        if sep and label and gloss:
            glosses[label] = gloss
    return glosses


def build_verify_messages(sets):
    """Chat messages asking the model to check ``sets``.

    ``sets`` is a list of ``(set_id, canonical, members)``; each member is a
    ``(label, name, gloss)`` tuple, the gloss empty for an English tag.
    """
    lines = []
    for set_id, canonical, members in sets:
        lines.append(f"Set {set_id}: {canonical}")
        for label, name, gloss in members:
            clean = " ".join(str(name).split())[:100]
            suffix = f" (English: {gloss})" if gloss else ""
            lines.append(f"{label}. {clean}{suffix}")
        lines.append("")
    return [
        {"role": "system", "content": VERIFY_PROMPT},
        {"role": "user", "content": "\n".join(lines).rstrip()},
    ]


def parse_verify_response(content, set_ids):
    """Labels kept by each set of the verification reply: ``{set id: [labels]}``.

    Raises ``LLMParseError`` when the reply is not a JSON object with a ``sets`` list,
    or when one of ``set_ids`` gets no usable answer. Malformed items are skipped, so
    their set counts as unanswered.
    """
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end <= start:
        raise llm_service.LLMParseError("no JSON object in verification reply")
    try:
        data = json.loads(content[start:end + 1])
    except ValueError as exc:
        raise llm_service.LLMParseError(f"invalid JSON in verification reply: {exc}") from exc
    raw_sets = data.get("sets") if isinstance(data, dict) else None
    if not isinstance(raw_sets, list):
        raise llm_service.LLMParseError("verification reply has no 'sets' list")

    wanted = set(set_ids)
    answers = {}
    for item in raw_sets:
        set_id = item.get("set") if isinstance(item, dict) else None
        if not isinstance(set_id, str) or set_id not in wanted:
            continue
        keep = item.get("keep")
        if isinstance(keep, list):
            answers[set_id] = [label for label in keep if isinstance(label, str)]
    for set_id in set_ids:
        if set_id not in answers:
            raise llm_service.LLMParseError(f"verification reply has no answer for set {set_id}")
    return answers


def plan_sets(sets):
    """Resolve, for each proposed set, the members and the tag it will merge into.

    The survivor is the tag ``Tag.find`` already knows by the canonical name
    (an existing tag or an alias, possibly outside the group). Otherwise it is
    the most-used member, which is then renamed to the canonical name. Sets with
    fewer than two live members are dropped. Returns ``(plans, usage)``.
    """
    all_ids = {pk for proposed in sets for pk in proposed["members"]}
    live = Tag.objects.in_bulk(list(all_ids))

    resolved = []
    for proposed in sets:
        members = [live[pk] for pk in proposed["members"] if pk in live]
        if len(members) < 2:
            continue
        resolved.append((proposed, members, Tag.find(proposed["canonical"])))

    usage = tag_usage(
        {tag.pk for _, members, _ in resolved for tag in members}
        | {existing.pk for _, _, existing in resolved if existing is not None}
    )

    plans = []
    for proposed, members, existing in resolved:
        member_ids = {tag.pk for tag in members}
        if existing is not None:
            survivor, rename = existing, False
        else:
            survivor = max(members, key=lambda tag: (usage.get(tag.pk, 0), -tag.pk))
            rename = True
        plans.append({
            "proposed": proposed,
            "members": members,
            "survivor": survivor,
            "rename": rename,
            "outside": existing is not None and existing.pk not in member_ids,
            "ids": member_ids | {survivor.pk},
        })
    return plans, usage


def review_reasons(plans, usage):
    """Why proposed sets must wait for a human. Empty list means safe to apply.

    The confidence is not checked here: the candidate's ``decide`` owns that.
    """
    big_usage = settings.TAG_BIG_TAG_USAGE
    blocked = blocked_pairs(Candidate.KIND_TAG_MERGE)

    reasons = []
    for plan in plans:
        proposed = plan["proposed"]
        name = proposed["canonical"]
        if plan["outside"]:
            reasons.append(
                f"'{name}' merges into existing tag '{plan['survivor'].name}' outside the group"
            )
        if sum(1 for pk in plan["ids"] if usage.get(pk, 0) > big_usage) >= 2:
            reasons.append(f"'{name}' joins several widely used tags")
        if any(pair_key(a, b) in blocked for a, b in combinations(sorted(plan["ids"]), 2)):
            reasons.append(f"'{name}' contains a pair marked as not mergeable")
    return reasons


class PlanChanged(Exception):
    """The tags changed between planning and taking the lock: the answer is stale."""


class NeedsReview(Exception):
    """Under the lock the plan is unchanged but a safeguard now trips."""

    def __init__(self, reasons):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def _plan_signature(plans):
    return sorted(
        (
            plan["proposed"]["canonical"],
            plan["survivor"].pk,
            plan["rename"],
            tuple(sorted(plan["ids"])),
        )
        for plan in plans
    )


def candidate_sets(candidate):
    """The sets the LLM proposed for one tag_merge candidate (its verdict)."""
    return (candidate.verdict or {}).get("sets") or []


def _apply_set(plan, candidate):
    """Run one planned set. Returns the undo entries of what it changed."""
    entries = []
    survivor = plan["survivor"]
    if not Tag.objects.filter(pk=survivor.pk).exists():
        raise MergeError(f"'{survivor.name}' was merged away while this cluster was applied.")
    if plan["rename"]:
        entry = apply_rename(survivor, plan["proposed"]["canonical"])
        if entry is not None:
            entries.append(entry)
    for tag in plan["members"]:
        if tag.pk == survivor.pk:
            continue
        # A member may already be gone if an earlier set in this cluster merged it.
        if Tag.objects.filter(pk=tag.pk).exists():
            entries.append(fold_tag(tag, survivor, candidate=candidate))
    return entries


def apply_sets(candidate):
    """Apply the sets of a tag_merge candidate and return the undo entries of the change.

    The caller holds the transaction. The candidate's tags are locked first, then
    planned again under those locks. A plan that changed since the first look writes
    nothing and raises ``PlanChanged``; a safeguard that trips under the lock raises
    ``NeedsReview``. A ``MergeError`` rolls the caller's transaction back.
    """
    sets = candidate_sets(candidate)
    plans, usage = plan_sets(sets)
    if not plans:
        raise PlanChanged("no set has two live tags left")

    involved = {pk for plan in plans for pk in plan["ids"]}
    signature = _plan_signature(plans)
    if lock_pks(Tag, involved) != involved:
        raise PlanChanged("a tag of the plan was merged away or deleted")
    fresh, fresh_usage = plan_sets(sets)
    if _plan_signature(fresh) != signature:
        raise PlanChanged("the tags changed since the plan was made")
    # Same plan, but a safeguard may trip now that usage is read under the lock.
    reasons = review_reasons(fresh, fresh_usage)
    if reasons:
        raise NeedsReview(reasons)

    entries = []
    for plan in fresh:
        entries.extend(_apply_set(plan, candidate))
    return entries
