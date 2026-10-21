import json

from django.conf import settings
from django.contrib import admin, messages
from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.html import format_html

from ..models import LLMProviderCooldown, LLMRequest, LLMUsage
from ..services import llm_service, llm_tasks


def _pretty_json(value):
    if value is None:
        return "-"
    return format_html(
        '<pre style="white-space:pre-wrap">{}</pre>',
        json.dumps(value, indent=2, ensure_ascii=False),
    )


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
    """Today's LLMUsage per task against the shared daily caps, and the last minute (see llm_service.can_afford)."""
    today = timezone.localdate()
    by_purpose = {
        row["purpose"]: row
        for row in LLMUsage.objects.filter(created_at__date=today)
        .values("purpose")
        .annotate(requests=Count("id"), tokens=Sum("tokens"))
    }
    rows = [
        {
            "label": task.label,
            "requests": by_purpose.get(task.name, {}).get("requests", 0),
            "tokens": by_purpose.get(task.name, {}).get("tokens") or 0,
        }
        for task in llm_tasks.REGISTRY.values()
    ]
    minute_requests, minute_tokens = llm_service.minute_usage()
    return {
        "date": today,
        "rows": rows,
        "requests": sum(r["requests"] for r in rows),
        "tokens": sum(r["tokens"] for r in rows),
        "requests_cap": settings.LLM_DAILY_REQUESTS,
        "tokens_cap": settings.LLM_DAILY_TOKENS,
        "minute": {
            "requests": minute_requests,
            "tokens": minute_tokens,
            "requests_cap": settings.LLM_REQUESTS_PER_MINUTE,
            "tokens_cap": settings.LLM_TOKENS_PER_MINUTE,
        },
        "providers": _providers_today(),
    }


@admin.register(LLMRequest)
class LLMRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "task", "status", "attempts", "tokens", "target_count", "created_at", "finished_at")
    list_filter = ("task", "status", "prompt_version")
    search_fields = ("error",)
    readonly_fields = (
        "task",
        "target_type",
        "target_ids",
        "status",
        "attempts",
        "not_before",
        "model",
        "prompt_version",
        "pretty_response",
        "raw_response",
        "error",
        "tokens",
        "created_at",
        "finished_at",
    )
    exclude = ("response",)
    actions = ["requeue", "reapply_result"]
    change_list_template = "admin/lncrawler_api/llmrequest/change_list.html"

    def has_add_permission(self, request):
        return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["llm_usage"] = _usage_today()
        return super().changelist_view(request, extra_context=extra_context)

    @admin.display(description="Targets")
    def target_count(self, obj):
        return len(obj.target_ids or [])

    @admin.display(description="Response")
    def pretty_response(self, obj):
        return _pretty_json(obj.response)

    @admin.action(description="Requeue selected requests")
    def requeue(self, request, queryset):
        # A RUNNING row is mid-call: requeuing it would make a second, duplicate call.
        updated = queryset.exclude(status=LLMRequest.STATUS_RUNNING).update(
            status=LLMRequest.STATUS_PENDING,
            attempts=0,
            not_before=None,
            error="",
            finished_at=None,
        )
        self.message_user(request, f"{updated} request(s) requeued.", messages.SUCCESS)

    @admin.action(description="Re-apply result of selected done requests")
    def reapply_result(self, request, queryset):
        applied = skipped = 0
        for req in queryset.filter(status=LLMRequest.STATUS_DONE):
            task = llm_tasks.REGISTRY.get(req.task)
            # A "skipped" response is run_queue closing a request without a call, not a result.
            if task is None or req.response is None or "skipped" in req.response:
                skipped += 1
                continue
            task.apply(req, req.response)
            applied += 1
        self.message_user(
            request,
            f"Re-applied {applied} result(s); skipped {skipped}.",
            messages.SUCCESS if applied else messages.WARNING,
        )
