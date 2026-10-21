# One-off export of labelled novel pairs to evaluate the novel merge judge.
# Not part of the app: run it on prod, send back the JSON, then delete this file.
#
#   docker cp merge_eval_export.py lncrawler-api-1:/tmp/merge_eval_export.py
#   docker exec lncrawler-api-1 sh -c 'cd /app/lncrawler-api && python manage.py shell < /tmp/merge_eval_export.py'
#   docker cp lncrawler-api-1:/tmp/merge_eval.json merge_eval.json
import json
import random

from django.db.models import Count

from lncrawler_api.models import MergeCandidate, Novel

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
wrong = MergeCandidate.objects.filter(novel_a__isnull=False, novel_b__isnull=False).filter(
    status=MergeCandidate.STATUS_PENDING, llm_verdict__same=True,
) | MergeCandidate.objects.filter(
    novel_a__isnull=False, novel_b__isnull=False, status=MergeCandidate.STATUS_REJECTED,
)
wrong = list(wrong.distinct())
random.shuffle(wrong)
for c in wrong[:LIMIT]:
    pairs.append({
        "label": "different", "origin": c.status, "candidate": str(c.pk),
        "old_verdict": c.llm_verdict,
        "a": novel_profile(c.novel_a), "b": novel_profile(c.novel_b),
    })

# Same works: novels you merged by hand that hold sources from two different sites.
survivors = Novel.objects.filter(
    pk__in=[
        c.novel_a_id or c.novel_b_id
        for c in MergeCandidate.objects.filter(
            status=MergeCandidate.STATUS_MERGED, decision=MergeCandidate.DECISION_REVIEW,
        )
        if (c.novel_a_id or c.novel_b_id)
    ]
).annotate(sites=Count("sources__external_source", distinct=True)).filter(sites__gte=2)
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
