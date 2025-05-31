from django.contrib import admin
from ..models import Board, Comment


# Inline for showing comments in Board admin
class BoardCommentInline(admin.TabularInline):
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


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "description_preview",
        "created_at",
        "comment_count",
        "is_active",
    )
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("id", "created_at", "comment_count")
    list_filter = ("is_active", "created_at")
    inlines = [BoardCommentInline]

    def description_preview(self, obj):
        preview = obj.description[:50] + "..." if len(obj.description) > 50 else obj.description
        return preview

    description_preview.short_description = "Description"
