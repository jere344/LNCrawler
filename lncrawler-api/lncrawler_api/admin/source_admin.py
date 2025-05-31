from django.contrib import admin
from ..models import (
    NovelFromSource,
    Author,
    Editor,
    Translator,
    Tag,
    Chapter,
    SourceVote,
    Volume,
)
from django.utils.html import format_html
from django.urls import reverse


# Register all novel-related models
@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Editor)
class EditorAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Translator)
class TranslatorAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "source_count")
    search_fields = ("name",)
    ordering = ("name",)

    def source_count(self, obj):
        return obj.novels.count()

    source_count.short_description = "Novel From Source Count"


# Add inline for showing votes in NovelFromSource admin
class SourceVoteInline(admin.TabularInline):
    model = SourceVote
    extra = 0
    fields = ("ip_address", "vote_type", "created_at")
    readonly_fields = ("ip_address", "created_at")
    can_delete = True
    max_num = 100  # Limit displayed votes


@admin.register(NovelFromSource)
class NovelFromSourceAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "source_name",
        "link_to_novel",
        "status",
        "chapters_count",
        "vote_score_display",
        "last_chapter_update",
        "id",
    )
    list_filter = ("source_name", "status", "language")
    search_fields = ("title", "novel__title", "source_name")
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "chapters_count",
        "link_to_novel",
        "upvotes",
        "downvotes",
        "vote_score",
        "view_chapters_link",
    )
    raw_id_fields = ("novel",)
    inlines = [SourceVoteInline]  # Removed ChapterInline

    def link_to_novel(self, obj):
        url = reverse("admin:lncrawler_api_novel_change", args=[obj.novel.id])
        return format_html('<a href="{}">{}</a>', url, obj.novel.title)

    link_to_novel.short_description = "Novel"

    def vote_score_display(self, obj):
        return obj.vote_score

    vote_score_display.short_description = "Vote Score"

    def delete_queryset(self, request, queryset):
        """
        Override the default delete_queryset method to call delete() on each object
        This ensures the model's delete method runs for bulk deletions from the list page
        """
        for obj in queryset:
            obj.delete()

    def view_chapters_link(self, obj):
        if obj.pk:
            url = f"/admin/lncrawler_api/chapter/?novel_from_source__id__exact={obj.pk}"
            return format_html('<a href="{}" target="_blank">View Chapters ({})</a>', url, obj.chapters_count)
        return "Save first to view chapters"

    view_chapters_link.short_description = "Chapters"


@admin.register(Volume)
class VolumeAdmin(admin.ModelAdmin):
    list_display = ("title", "novel_from_source", "volume_id", "chapter_count")
    list_filter = ("novel_from_source__source_name",)
    search_fields = ("title", "novel_from_source__title")
    raw_id_fields = ("novel_from_source",)


# Register new models
@admin.register(SourceVote)
class SourceVoteAdmin(admin.ModelAdmin):
    list_display = ("source", "ip_address", "vote_type", "created_at")
    list_filter = ("vote_type", "created_at")
    search_fields = ("source__title", "ip_address")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("source",)
