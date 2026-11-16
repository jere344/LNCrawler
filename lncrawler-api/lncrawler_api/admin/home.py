"""Admin home page: what waits for review, the maintenance tools, what is broken, the harvest and the scheduled tasks.

The index shows these sections next to the regrouped sidebar (see app_groups.py).
Each section is built only for users holding the permission behind its links, and
every query is a count or a short list.
"""
from django.contrib import admin
from django.db.models import Count
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from .scheduler_admin import operations_context
from ..models import (
    AudiobookWorker,
    Candidate,
    HarvestCandidate,
    LLMProviderCooldown,
    Novel,
    PlaceholderCover,
    ScheduledTask,
    Tag,
)

HOME_TEMPLATE = "admin/lncrawler_api/home.html"

# (label, url name, model, action whose permission on the model guards the tool). A tool whose URL
# is not registered (yet) is left out instead of breaking the page.
TOOLS = [
    ("Novel merge", "admin:lncrawler_api_novel_merge", Novel, "change"),
    ("Novel split", "admin:lncrawler_api_novel_split", Novel, "change"),
    ("Tag merge", "admin:lncrawler_api_tag_merge", Tag, "change"),
    ("Duplicate covers", "admin:lncrawler_api_placeholdercover_duplicates", PlaceholderCover, "change"),
    ("Audiobook workers: new token", "admin:lncrawler_api_audiobookworker_token", AudiobookWorker, "add"),
]


def _can(request, model, action):
    meta = model._meta
    return request.user.has_perm(f"{meta.app_label}.{action}_{meta.model_name}")


def _reverse_or_none(name):
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


def _review_section(request):
    kinds = []
    if _can(request, Candidate, "change"):
        # Same count as the per-kind review links in candidate_admin, in one query.
        counts = {
            row["kind"]: row["total"]
            for row in Candidate.objects.filter(status=Candidate.STATUS_REVIEW)
            .values("kind")
            .annotate(total=Count("pk"))
        }
        kinds = [
            {
                "url": reverse("admin:lncrawler_api_candidate_review", args=[kind]),
                "label": label,
                "count": counts.get(kind, 0),
            }
            for kind, label in Candidate.KIND_CHOICES
        ]

    failed_harvest = None
    if _can(request, HarvestCandidate, "view"):
        failed_harvest = {
            "url": reverse("admin:lncrawler_api_harvestcandidate_changelist")
            + f"?status__exact={HarvestCandidate.STATUS_FAILED}",
            "count": HarvestCandidate.objects.filter(status=HarvestCandidate.STATUS_FAILED).count(),
        }

    if not kinds and failed_harvest is None:
        return None
    return {"kinds": kinds, "failed_harvest": failed_harvest}


def _tools_section(request):
    tools = []
    for label, url_name, model, action in TOOLS:
        if not _can(request, model, action):
            continue
        url = _reverse_or_none(url_name)
        if url:
            tools.append({"label": label, "url": url})
    return tools or None


def _attention_section(request):
    show_tasks = _can(request, ScheduledTask, "view")
    show_cooldowns = _can(request, LLMProviderCooldown, "view")
    if not show_tasks and not show_cooldowns:
        return None

    now = timezone.now()
    failed_tasks, expired_locks, cooldowns = [], [], []
    if show_tasks:
        failed_tasks = list(ScheduledTask.objects.filter(status="failed").order_by("name"))
        expired_locks = list(
            ScheduledTask.objects.filter(status="running", locked_until__lt=now).order_by("locked_until")
        )
    if show_cooldowns:
        cooldowns = list(LLMProviderCooldown.objects.filter(until__gt=now).order_by("until"))
    return {
        "failed_tasks": failed_tasks,
        "expired_locks": expired_locks,
        "cooldowns": cooldowns,
        "has_problems": bool(failed_tasks or expired_locks or cooldowns),
    }


_original_index = admin.site.index


def _index_with_home(request, extra_context=None):
    home = {
        "review": _review_section(request),
        "tools": _tools_section(request),
        "attention": _attention_section(request),
        "operations": operations_context(request),
    }
    return _original_index(request, {**(extra_context or {}), "home": home})


admin.site.index = _index_with_home
admin.site.index_template = HOME_TEMPLATE
