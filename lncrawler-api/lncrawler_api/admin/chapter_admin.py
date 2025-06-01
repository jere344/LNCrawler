from django.contrib import admin
from ..models import Chapter, Comment
from django.utils.html import format_html
from django.urls import reverse


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
        preview = obj.message[:30] + "..." if len(obj.message) > 30 else obj.message
        return preview
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
    list_filter = ("novel_from_source__external_source__source_name", "volume", "has_content")
    search_fields = ("title", "novel_from_source__title")
    raw_id_fields = ("novel_from_source",)
    readonly_fields = ("comment_count",)
    inlines = [ChapterCommentInline]

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
