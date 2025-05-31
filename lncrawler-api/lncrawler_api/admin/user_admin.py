from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from ..models import Comment, Review
from django.conf import settings
from django.contrib.auth import get_user_model
CustomUser = get_user_model()


# Inline for showing user comments
class UserCommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    fields = ("admin_link", "target_display", "message_preview", "contains_spoiler", "created_at", "vote_score")
    readonly_fields = ("admin_link", "target_display", "message_preview", "created_at", "vote_score")
    can_delete = False
    max_num = 20
    ordering = ("-created_at",)

    def admin_link(self, obj):
        if obj.pk:
            url = f"/admin/lncrawler_api/comment/{obj.pk}/change/"
            return format_html('<a href="{}">{}</a>', url, f"Comment #{obj.pk}")
        return ""
    admin_link.short_description = "Edit"

    def target_display(self, obj):
        if obj.novel:
            return f"Novel: {obj.novel.title}"
        elif obj.chapter:
            return f"Chapter: {obj.chapter.title}"
        elif obj.board:
            return f"Board: {obj.board.name}"
        return "Unknown"
    target_display.short_description = "Target"

    def message_preview(self, obj):
        preview = obj.message[:30] + "..." if len(obj.message) > 30 else obj.message
        return preview
    message_preview.short_description = "Message"

    def vote_score(self, obj):
        return obj.vote_score
    vote_score.short_description = "Vote Score"


# Inline for showing user reviews
class UserReviewInline(admin.TabularInline):
    model = Review
    extra = 0
    fields = ("admin_link", "novel", "content_preview", "created_at", "get_reaction_count")
    readonly_fields = ("admin_link", "content_preview", "created_at", "get_reaction_count")
    can_delete = False
    max_num = 5
    ordering = ("-created_at",)

    def admin_link(self, obj):
        if obj.pk:
            url = f"/admin/lncrawler_api/review/{obj.pk}/change/"
            return format_html('<a href="{}">{}</a>', url, f"Review #{obj.pk}")
        return ""
    admin_link.short_description = "Edit"

    def content_preview(self, obj):
        preview = obj.content[:50] + "..." if len(obj.content) > 50 else obj.content
        return preview
    content_preview.short_description = "Content"


# Extend the default User admin
class CustomUserAdmin(UserAdmin):
    inlines = UserAdmin.inlines + (
        UserCommentInline,
        UserReviewInline,
    )


# Unregister the default User admin and register our custom one
admin.site.register(CustomUser, CustomUserAdmin)
