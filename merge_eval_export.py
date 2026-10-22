# One-off export of labelled novel pairs to evaluate the novel merge judge.
# Not part of the app: run it on prod, send back the JSON, then delete this file.
#
#   docker cp merge_eval_export.py lncrawler-api-1:/tmp/merge_eval_export.py
#   docker exec lncrawler-api-1 sh -c 'cd /app/lncrawler-api && python manage.py shell < /tmp/merge_eval_export.py'
#   docker cp lncrawler-api-1:/tmp/merge_eval.json merge_eval.json
import json
import random

from django.db.models import Count, Q

from lncrawler_api.models import Candidate, Novel

LIMIT = 60
random.seed(1)


def source_profile(src):
    return {
        "title": src.title or "",
        "titles": [src.title] if src.title else [],
        "alternative_titles": sorted(a.name for a in src.alternative_titles.all()),
        "authors": sorted(a.name for a in src.authors.all()),
        "languages": [src.language] if src.language else [],
        "synopsis": (src.synopsis or "")[:600],
    }


def novel_profile(novel):
    sources = list(novel.sources.all())
    titles, alts, authors, languages, synopsis = [], set(), set(), set(), ""
    for src in sources:
        if src.title and src.title not in titles:
            titles.append(src.title)
        if src.language:
            languages.add(src.language)
        if not synopsis and src.synopsis:
            synopsis = src.synopsis
        authors.update(a.name for a in src.authors.all())
        alts.update(a.name for a in src.alternative_titles.all())
    return {
        "title": novel.title or (titles[0] if titles else ""),
        "titles": titles,
        "alternative_titles": sorted(alts),
        "authors": sorted(authors),
        "languages": sorted(languages),
        "synopsis": (synopsis or "")[:600],
    }


pairs = []

# Different works: the confident "same" pile (reviewed as wrong) and rejected pairs.
# A novel_merge verdict stores the answer as "yes" (same) or "no" (different).
wrong = list(
    Candidate.objects.filter(kind=Candidate.KIND_NOVEL_MERGE).filter(
        Q(status=Candidate.STATUS_REVIEW, verdict__answer="yes")
        | Q(status=Candidate.STATUS_REJECTED)
    )
)
random.shuffle(wrong)
for c in wrong:
    found = {str(novel.pk): novel for novel in Novel.objects.filter(pk__in=c.target_ids)}
    if len(found) != 2:
        continue
    a, b = (found[str(pk)] for pk in c.target_ids)
    pairs.append({
        "label": "different", "origin": c.status, "candidate": str(c.pk),
        "old_verdict": c.verdict,
        "a": novel_profile(a), "b": novel_profile(b),
    })
    if sum(p["label"] == "different" for p in pairs) >= LIMIT:
        break

# Same works: novels you merged by hand that hold sources from two different sites.
# A merged novel is the survivor of an applied novel_merge candidate decided by a human.
# Both ids of the pair are read: the merged-away one no longer exists, so the query below drops it.
survivor_ids = {
    pk
    for c in Candidate.objects.filter(
        kind=Candidate.KIND_NOVEL_MERGE, status=Candidate.STATUS_APPLIED,
        decided_by=Candidate.DECIDED_HUMAN,
    )
    for pk in c.target_ids
}
survivors = Novel.objects.filter(pk__in=list(survivor_ids)).annotate(
    sites=Count("sources__external_source", distinct=True)
).filter(sites__gte=2)
survivors = list(survivors)
random.shuffle(survivors)
for novel in survivors[:LIMIT]:
    by_site = {}
    for src in novel.sources.all():
        by_site.setdefault(src.external_source_id, src)
    first, second = list(by_site.values())[:2]
    pairs.append({
        "label": "same", "origin": "human merge", "novel": str(novel.pk),
        "a": source_profile(first), "b": source_profile(second),
    })

with open("/tmp/merge_eval.json", "w") as f:
    json.dump(pairs, f, ensure_ascii=False, indent=1)
print(f"wrote {len(pairs)} pairs to /tmp/merge_eval.json "
      f"({sum(p['label'] == 'different' for p in pairs)} different, "
      f"{sum(p['label'] == 'same' for p in pairs)} same)")
