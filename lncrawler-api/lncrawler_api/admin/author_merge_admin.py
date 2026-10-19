from django.contrib import admin, messages
from django.utils import timezone

from ..models import AuthorAlias, AuthorMerge, AuthorMergeCandidate
from ..services.author_merge_service import merge_candidate, undo_author_merge
from ..services.merge_service import MergeError
from .tag_merge_admin import _pretty_json


@admin.register(AuthorMergeCandidate)
class AuthorMergeCandidateAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "names", "reason", "created_at")
    list_filter = ("status", "reason")
    ordering = ("-created_at",)
    fields = (
        "status",
        "author_names",
        "author_ids",
        "reason",
        "signature",
        "signals_pretty",
        "llm_response_pretty",
        "llm_model",
        "decided_at",
        "created_at",
        "updated_at",
    )
    readonly_fields = fields
    actions = (
        "apply_merges",
        "reject_candidates",
        "undo_merges",
    )

    def has_add_permission(self, request):
        return False

    def names(self, obj):
        return ", ".join(obj.author_names)

    names.short_description = "Names"

    def signals_pretty(self, obj):
        return _pretty_json(obj.signals)

    signals_pretty.short_description = "Signals"

    def llm_response_pretty(self, obj):
        return _pretty_json(obj.llm_response)

    llm_response_pretty.short_description = "LLM response"

    @admin.action(description="Apply the merge (most-used author survives)")
    def apply_merges(self, request, queryset):
        applied = 0
        for candidate in queryset.filter(
            status__in=[AuthorMergeCandidate.STATUS_PENDING, AuthorMergeCandidate.STATUS_REVIEW]
        ):
            if merge_candidate(candidate) == "merged":
                applied += 1
            else:
                reason = candidate.signals.get("merge_error", candidate.reason)
                self.message_user(request, f"Candidate {candidate.pk}: {reason}", messages.ERROR)
        self.message_user(request, f"Applied {applied} candidate(s).", messages.SUCCESS)

    @admin.action(description="Reject: never propose these pairs again")
    def reject_candidates(self, request, queryset):
        count = queryset.filter(
            status__in=[
                AuthorMergeCandidate.STATUS_PENDING,
                AuthorMergeCandidate.STATUS_REVIEW,
                AuthorMergeCandidate.STATUS_ERROR,
            ]
        ).update(status=AuthorMergeCandidate.STATUS_REJECTED, decided_at=timezone.now())
        self.message_user(request, f"Rejected {count} candidate(s).", messages.SUCCESS)

    @admin.action(description="Undo applied merges")
    def undo_merges(self, request, queryset):
        undone = 0
        for candidate in queryset.filter(status=AuthorMergeCandidate.STATUS_APPLIED):
            for merge in candidate.merges.filter(undone_at__isnull=True):
                try:
                    undo_author_merge(merge)
                except MergeError as exc:
                    self.message_user(request, f"Candidate {candidate.pk}: {exc}", messages.ERROR)
                else:
                    undone += 1
        self.message_user(request, f"Undid {undone} merge(s).", messages.SUCCESS)


@admin.register(AuthorMerge)
class AuthorMergeAdmin(admin.ModelAdmin):
    list_display = ("source_name", "target_name", "candidate", "created_at", "undone_at")
    search_fields = ("source_name", "target_name")
    list_select_related = ("candidate",)
    fields = (
        "source_name",
        "target",
        "target_name",
        "candidate",
        "source_ids",
        "added_source_ids",
        "moved_alias_ids",
        "created_at",
        "undone_at",
    )
    readonly_fields = fields
    actions = ("undo_merges",)

    def has_add_permission(self, request):
        return False

    @admin.action(description="Undo selected merges")
    def undo_merges(self, request, queryset):
        undone = 0
        for merge in queryset.filter(undone_at__isnull=True):
            try:
                undo_author_merge(merge)
            except MergeError as exc:
                self.message_user(request, f"{merge}: {exc}", messages.ERROR)
            else:
                undone += 1
        self.message_user(request, f"Undid {undone} merge(s).", messages.SUCCESS)


@admin.register(AuthorAlias)
class AuthorAliasAdmin(admin.ModelAdmin):
    list_display = ("name", "author", "created_at")
    search_fields = ("name", "author__name")
    raw_id_fields = ("author",)
