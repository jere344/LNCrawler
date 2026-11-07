from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from ..models.chat_models import ChatMessage
from .display import parent_link, truncate


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
        return truncate(obj.message, 50)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("author_name", "message_preview", "contains_spoiler", "created_at", "user")
    list_filter = ("contains_spoiler", "created_at")
    search_fields = ("author_name", "message")
    readonly_fields = ("id", "created_at", "parent_message")
    raw_id_fields = ("user", "parent")
    inlines = [ChatReplyInline]

    def message_preview(self, obj):
        return truncate(obj.message, 60)

    message_preview.short_description = "Message"

    def parent_message(self, obj):
        return parent_link(obj, "admin:lncrawler_api_chatmessage_change", "Top-level message")

    parent_message.short_description = "Parent Message"
