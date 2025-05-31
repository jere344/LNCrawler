from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from ..models import (
    Comment,
    CommentVote,
    Board,
)


# Inline for showing comment votes in Comment admin
class CommentVoteInline(admin.TabularInline):
    model = CommentVote
    extra = 0
    fields = ("ip_address", "vote_type", "created_at")
    readonly_fields = ("ip_address", "created_at")
    can_delete = True
    max_num = 100  # Limit displayed votes


# Inline for showing replies in Comment admin
class CommentReplyInline(admin.TabularInline):
    model = Comment
    extra = 0
    fields = ("reply_link", "message_preview", "contains_spoiler", "created_at", "vote_score")
    readonly_fields = ("reply_link", "message_preview", "created_at", "vote_score")
    can_delete = True
    verbose_name = "Reply"
    verbose_name_plural = "Replies"
    fk_name = "parent"  # Specify which foreign key to use

    def vote_score(self, obj):
        return obj.vote_score

    def reply_link(self, obj):
        url = reverse("admin:lncrawler_api_comment_change", args=[obj.id])
        return format_html('<a href="{}">{}</a>', url, obj.author_name)
    
    def message_preview(self, obj):
        url = reverse("admin:lncrawler_api_comment_change", args=[obj.id])
        preview = obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
        return format_html('<a href="{}">{}</a>', url, preview)

    vote_score.short_description = "Vote Score"
    reply_link.short_description = "Author"
    message_preview.short_description = "Message"


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = (
        "author_name",
        "target_display",
        "message_preview",
        "contains_spoiler",
        "created_at",
        "vote_score_display",
        "reply_count",
    )
    list_filter = ("contains_spoiler", "created_at")
    search_fields = ("author_name", "message", "novel__title", "chapter__title")
    readonly_fields = (
        "id",
        "created_at",
        "vote_score_display",
        "parent_comment",
        "target_link",
    )
    raw_id_fields = ("novel", "chapter", "parent")
    fieldsets = (
        (
            "Comment Information",
            {
                "fields": (
                    "id",
                    "author_name",
                    "target_link",
                    "parent_comment",
                    "contains_spoiler",
                    "created_at",
                )
            },
        ),
        ("Content", {"fields": ("message",)}),
        ("Votes", {"fields": ("upvotes", "downvotes", "vote_score_display")}),
        ("Source", {"fields": ("ip_address",)}),
    )
    inlines = [CommentReplyInline, CommentVoteInline]

    def message_preview(self, obj):
        # Truncate long messages for display in the list
        preview = obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
        return preview

    message_preview.short_description = "Message"

    def vote_score_display(self, obj):
        return obj.vote_score

    vote_score_display.short_description = "Vote Score"

    def reply_count(self, obj):
        return obj.replies.count()

    reply_count.short_description = "Replies"

    def target_display(self, obj):
        if obj.novel:
            return f"Novel: {obj.novel.title}"
        elif obj.chapter:
            return f"Chapter: {obj.chapter.title}"
        elif obj.board:
            return f"Board: {obj.board.name}"
        return "Unknown"

    target_display.short_description = "Target"

    def parent_comment(self, obj):
        if obj.parent:
            url = reverse("admin:lncrawler_api_comment_change", args=[obj.parent.id])
            return format_html('<a href="{}">{}</a>', url, f"Reply to: {obj.parent.author_name}")
        return "Top-level comment"

    parent_comment.short_description = "Parent Comment"

    def target_link(self, obj):
        if obj.novel:
            url = reverse("admin:lncrawler_api_novel_change", args=[obj.novel.id])
            return format_html('<a href="{}">{}</a>', url, obj.novel.title)
        elif obj.chapter:
            url = reverse("admin:lncrawler_api_chapter_change", args=[obj.chapter.id])
            return format_html('<a href="{}">{}</a>', url, obj.chapter.title)
        elif obj.board:
            url = reverse("admin:lncrawler_api_board_change", args=[obj.board.id])
            return format_html('<a href="{}">{}</a>', url, obj.board.name)
        return "Unknown"

    target_link.short_description = "Target"


@admin.register(CommentVote)
class CommentVoteAdmin(admin.ModelAdmin):
    list_display = ("comment_preview", "ip_address", "vote_type", "created_at")
    list_filter = ("vote_type", "created_at")
    search_fields = ("comment__message", "comment__author_name", "ip_address")
    readonly_fields = ("created_at", "updated_at", "comment_link")
    raw_id_fields = ("comment",)

    def comment_preview(self, obj):
        preview = (
            obj.comment.message[:30] + "..."
            if len(obj.comment.message) > 30
            else obj.comment.message
        )
        return f"{obj.comment.author_name}: {preview}"

    comment_preview.short_description = "Comment"

    def comment_link(self, obj):
        url = reverse("admin:lncrawler_api_comment_change", args=[obj.comment.id])
        return format_html('<a href="{}">{}</a>', url, f"Comment by {obj.comment.author_name}")

    comment_link.short_description = "Comment"
