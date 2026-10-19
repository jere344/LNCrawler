import json

from django.contrib import admin, messages
from django.utils.html import format_html

from ..models import LLMRequest
from ..services import llm_tasks


def _pretty_json(value):
    if value is None:
        return "-"
    return format_html(
        '<pre style="white-space:pre-wrap">{}</pre>',
        json.dumps(value, indent=2, ensure_ascii=False),
    )


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

    def has_add_permission(self, request):
        return False

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
            # A "skipped" response is run_task closing a request without a call, not a result.
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
