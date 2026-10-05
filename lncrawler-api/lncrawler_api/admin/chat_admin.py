from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from ..models.chat_models import ChatMessage


class ChatReplyInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    fields = ("reply_link", "message_preview", "contains_spoiler", "created_at")
    readonly_fields = ("reply_link", "message_preview", "created_at")
    can_delete = True
    verbose_name = "Reply"
    verbose_name_plural = "Replies"
    fk_name = "parent"

    def reply_link(self, obj):
        url = reverse("admin:lncrawler_api_chatmessage_change", args=[obj.id])
        return format_html('<a href="{}">{}</a>', url, obj.author_name)

    def message_preview(self, obj):
        preview = obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
        return preview


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("author_name", "message_preview", "contains_spoiler", "created_at", "user")
    list_filter = ("contains_spoiler", "created_at")
    search_fields = ("author_name", "message")
    readonly_fields = ("id", "created_at", "parent_message")
    raw_id_fields = ("user", "parent")
    inlines = [ChatReplyInline]

    def message_preview(self, obj):
        return obj.message[:60] + "..." if len(obj.message) > 60 else obj.message

    message_preview.short_description = "Message"

    def parent_message(self, obj):
        if obj.parent:
            url = reverse("admin:lncrawler_api_chatmessage_change", args=[obj.parent.id])
            return format_html('<a href="{}">{}</a>', url, f"Reply to: {obj.parent.author_name}")
        return "Top-level message"

    parent_message.short_description = "Parent Message"
