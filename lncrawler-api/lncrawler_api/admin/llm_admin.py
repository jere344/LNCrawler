from django.contrib import admin
from django.db.models import Count, Sum
from django.utils import timezone

from ..models import LLMCall, LLMProviderCooldown
from ..services import llm_service, llm_tasks


def _providers_today():
    """Per configured provider, in chain order: today's usage against its caps, the last minute and cooldown."""
    now = timezone.now()
    rows = []
    for provider in llm_service.providers():
        if not provider.configured:
            continue
        minute_requests, minute_tokens = llm_service.minute_usage(provider)
        cooling = LLMProviderCooldown.objects.filter(name=provider.name, until__gt=now).first()
        rows.append({
            "name": provider.name,
            "model": provider.model,
            "requests": llm_service.requests_used_today(provider),
            "tokens": llm_service.tokens_used_today(provider),
            "requests_cap": provider.daily_requests,
            "tokens_cap": provider.daily_tokens,
            "minute": {
                "requests": minute_requests,
                "tokens": minute_tokens,
                "requests_cap": provider.requests_per_minute,
                "tokens_cap": provider.tokens_per_minute,
            },
            "cooldown_until": cooling.until if cooling else None,
            "cooldown_reason": cooling.reason if cooling else "",
        })
    return rows


def _usage_today():
    """Today's LLMCall rows per task, and all LLMCall rows of the last minute."""
    today = timezone.localdate()
    by_kind = {
        row["kind"]: row
        # The copied request log is history only: the budget does not count it either.
        for row in LLMCall.objects.filter(created_at__date=today)
        .exclude(provider=llm_service.REQUEST_LOG_PROVIDER)
        .values("kind")
        .annotate(requests=Count("id"), tokens=Sum("tokens"))
    }
    rows = [
        {
            "label": task.label,
            "requests": by_kind.get(task.name, {}).get("requests", 0),
            "tokens": by_kind.get(task.name, {}).get("tokens") or 0,
        }
        for task in llm_tasks.REGISTRY.values()
    ]
    minute_requests, minute_tokens = llm_service.minute_usage()
    return {
        "date": today,
        "rows": rows,
        "requests": sum(r["requests"] for r in rows),
        "tokens": sum(r["tokens"] for r in rows),
        "minute": {
            "requests": minute_requests,
            "tokens": minute_tokens,
        },
        "providers": _providers_today(),
    }


@admin.register(LLMCall)
class LLMCallAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "provider", "model", "tokens", "created_at", "error_excerpt")
    list_filter = ("kind", "provider")
    search_fields = ("error",)
    readonly_fields = (
        "kind",
        "provider",
        "model",
        "prompt_version",
        "tokens",
        "candidate_ids",
        "error",
        "raw_response",
        "created_at",
    )
    change_list_template = "admin/lncrawler_api/llmcall/change_list.html"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # The log is the budget ledger and holds the raw replies review pages link to.
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["llm_usage"] = _usage_today()
        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(description="Error")
    def error_excerpt(self, obj):
        return (obj.error or "")[:120]
