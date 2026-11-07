from django.contrib import admin
from ..models import Chapter, Comment
from ..services.chapter_stats import refresh_chapter_stats
from django.utils.html import format_html
from django.urls import reverse
from .display import truncate
from .perf import CappedCountPaginator


# Inline for showing comments in Chapter admin
class ChapterCommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    fields = ("author_name", "message_preview", "contains_spoiler", "created_at", "vote_score")
    readonly_fields = ("created_at", "vote_score", "message_preview")
    can_delete = True
    max_num = 50  # Limit displayed comments
    ordering = ("-created_at",)

    def message_preview(self, obj):
        return truncate(obj.message, 30)
    message_preview.short_description = "Message"

    def vote_score(self, obj):
        return obj.vote_score
    vote_score.short_description = "Vote Score"


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "link_to_novel_source",
        "chapter_id",
        "volume",
        "has_content",
        "comment_count",
    )
    list_filter = ("novel_from_source__external_source__source_name", "has_content")
    search_fields = ("title", "novel_from_source__title")
    raw_id_fields = ("novel_from_source",)
    readonly_fields = ("comment_count",)
    inlines = [ChapterCommentInline]
    paginator = CappedCountPaginator
    show_full_result_count = False
    ordering = ("-id",)
    list_select_related = ("novel_from_source",)

    def link_to_novel_source(self, obj):
        url = reverse(
            "admin:lncrawler_api_novelfromsource_change",
            args=[obj.novel_from_source.id],
        )
        return format_html('<a href="{}">{}</a>', url, obj.novel_from_source.title)

    link_to_novel_source.short_description = "Novel From Source"

    def comment_count(self, obj):
        return obj.comments.count()
    comment_count.short_description = "Comments"

    # The chapter stats live on the source row: refresh every source a chapter
    # leaves or joins (ModelAdmin has no hook for this, so these wrap the save/delete).
    def save_model(self, request, obj, form, change):
        old_source_id = None
        if obj.pk is not None:
            old_source_id = Chapter.objects.filter(pk=obj.pk).values_list('novel_from_source_id', flat=True).first()
        super().save_model(request, obj, form, change)
        refresh_chapter_stats({old_source_id, obj.novel_from_source_id} - {None})

    def delete_model(self, request, obj):
        source_id = obj.novel_from_source_id
        super().delete_model(request, obj)
        refresh_chapter_stats([source_id])

    def delete_queryset(self, request, queryset):
        source_ids = set(queryset.values_list('novel_from_source_id', flat=True))
        super().delete_queryset(request, queryset)
        refresh_chapter_stats(source_ids)
