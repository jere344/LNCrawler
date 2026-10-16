import json

from django.contrib import admin, messages
from django.db.models import TextField
from django.db.models.functions import Cast
from django.utils.html import format_html

from ..models import TagCluster, TagMerge
from ..services import tag_merge_service as tms
from ..services.merge_service import MergeError, undo_tag_cluster, undo_tag_merge


def _pretty_json(value):
    if value is None:
        return "-"
    return format_html(
        '<pre style="white-space:pre-wrap">{}</pre>',
        json.dumps(value, indent=2, ensure_ascii=False),
    )


@admin.register(TagCluster)
class TagClusterAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "size", "names", "judged_at", "created_at")
    list_filter = ("status",)
    search_fields = ("tag_names",)
    ordering = ("-created_at",)
    fields = (
        "status",
        "tag_names",
        "tag_ids",
        "signature",
        "signals_pretty",
        "llm_response_pretty",
        "llm_model",
        "llm_batch",
        "judged_at",
        "error",
        "created_at",
        "updated_at",
    )
    readonly_fields = fields
    actions = (
        "apply_forced",
        "reject_clusters",
        "undo_clusters",
        "requeue_clusters",
    )

    def has_add_permission(self, request):
        return False

    def get_search_results(self, request, queryset, search_term):
        # tag_names is JSON, so search its text form rather than the value.
        if not search_term:
            return super().get_search_results(request, queryset, search_term)
        queryset = queryset.annotate(names_text=Cast("tag_names", TextField())).filter(
            names_text__icontains=search_term
        )
        return queryset, False

    def size(self, obj):
        return len(obj.tag_ids)

    size.short_description = "Tags"

    def names(self, obj):
        return ", ".join(obj.tag_names)

    names.short_description = "Names"

    def signals_pretty(self, obj):
        return _pretty_json(obj.signals)

    signals_pretty.short_description = "Signals"

    def llm_response_pretty(self, obj):
        return _pretty_json(obj.llm_response)

    llm_response_pretty.short_description = "LLM response"

    @admin.action(description="Apply proposed merges (ignore safeguards)")
    def apply_forced(self, request, queryset):
        applied = 0
        for cluster in queryset.filter(status=TagCluster.STATUS_REVIEW):
            if tms.apply_cluster(cluster, force=True) == TagCluster.STATUS_APPLIED:
                applied += 1
        self.message_user(request, f"Applied {applied} review cluster(s).", messages.SUCCESS)

    @admin.action(description="Reject: never propose the pairs in the proposed sets again")
    def reject_clusters(self, request, queryset):
        rejected = queryset.exclude(
            status__in=[TagCluster.STATUS_APPLIED, TagCluster.STATUS_UNDONE]
        )
        count = 0
        for cluster in rejected:
            tms.reject_cluster(cluster)
            count += 1
        self.message_user(request, f"Rejected {count} cluster(s).", messages.SUCCESS)

    @admin.action(description="Undo applied merges")
    def undo_clusters(self, request, queryset):
        undone = 0
        for cluster in queryset.filter(status=TagCluster.STATUS_APPLIED):
            try:
                undo_tag_cluster(cluster)
            except MergeError as exc:
                self.message_user(request, f"Cluster {cluster.pk}: {exc}", messages.ERROR)
            else:
                undone += 1
        self.message_user(request, f"Undid {undone} cluster(s).", messages.SUCCESS)

    @admin.action(description="Re-queue for judging (clears the LLM answer)")
    def requeue_clusters(self, request, queryset):
        count = queryset.filter(
            status__in=[
                TagCluster.STATUS_REVIEW,
                TagCluster.STATUS_ERROR,
                TagCluster.STATUS_NO_MERGE,
                TagCluster.STATUS_REJECTED,
            ]
        ).update(
            status=TagCluster.STATUS_PENDING,
            llm_response=None,
            llm_model="",
            llm_batch=None,
            judged_at=None,
            error="",
            requeue_count=0,
        )
        self.message_user(request, f"Re-queued {count} cluster(s).", messages.SUCCESS)


@admin.register(TagMerge)
class TagMergeAdmin(admin.ModelAdmin):
    list_display = ("kind", "source_name", "target_name", "cluster", "created_at", "undone_at")
    list_filter = ("kind",)
    search_fields = ("source_name", "target_name")
    list_select_related = ("cluster",)
    fields = (
        "kind",
        "source_name",
        "target",
        "target_name",
        "renamed_from",
        "cluster",
        "all_source_ids",
        "added_source_ids",
        "moved_alias_ids",
        "created_at",
        "undone_at",
    )
    readonly_fields = fields
    actions = ("undo_merges",)

    def has_add_permission(self, request):
        return False

    @admin.action(description="Undo selected changes")
    def undo_merges(self, request, queryset):
        undone = 0
        for merge in queryset.filter(undone_at__isnull=True):
            try:
                undo_tag_merge(merge)
            except MergeError as exc:
                self.message_user(request, f"{merge}: {exc}", messages.ERROR)
            else:
                undone += 1
        self.message_user(request, f"Undid {undone} change(s).", messages.SUCCESS)
