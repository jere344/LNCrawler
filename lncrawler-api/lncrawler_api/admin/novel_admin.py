from ..models import (
    Novel,
    NovelFromSource,
    NovelRating,
    NovelViewCount,
    WeeklyNovelView,
    FeaturedNovel,
    NovelSimilarity,
    Comment,
    Review,
)
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse


# Inline for showing sources in Novel admin
class NovelFromSourceInline(admin.TabularInline):
    model = NovelFromSource
    extra = 0
    fields = (
        "link_to_source",
        "external_source__source_name",
        "status",
        "chapters_count",
        "last_chapter_update",
    )
    readonly_fields = ("link_to_source", "chapters_count", "last_chapter_update")
    show_change_link = True
    can_delete = False

    def link_to_source(self, obj):
        url = reverse("admin:lncrawler_api_novelfromsource_change", args=[obj.id])
        return format_html('<a href="{}">{}</a>', url, obj.title)

    link_to_source.short_description = "Title"


# Inline for showing comments in Novel admin
class NovelCommentInline(admin.TabularInline):
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


# Inline for showing reviews in Novel admin
class NovelReviewInline(admin.TabularInline):
    model = Review
    extra = 0
    fields = ("user", "content_preview", "created_at", "get_reaction_count")
    readonly_fields = ("content_preview","created_at", "get_reaction_count")
    can_delete = True
    max_num = 20  # Limit displayed reviews
    ordering = ("-created_at",)

    def content_preview(self, obj):
        preview = obj.content[:50] + "..." if len(obj.content) > 50 else obj.content
        return preview
    content_preview.short_description = "Content"


@admin.register(Novel)
class NovelAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "slug",
        "sources_count",
        "comment_count",
        "view_count_display",
        "created_at",
        "updated_at",
    )
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "sources_count",
        "view_count_display",
        "comment_count",
    )
    inlines = [NovelFromSourceInline, NovelCommentInline, NovelReviewInline]

    def view_count_display(self, obj):
        try:
            return obj.view_count.views
        except NovelViewCount.DoesNotExist:
            return 0

    view_count_display.short_description = "Views"


@admin.register(NovelRating)
class NovelRatingAdmin(admin.ModelAdmin):
    list_display = ("novel", "ip_address", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("novel__title", "ip_address")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("novel",)


@admin.register(NovelViewCount)
class NovelViewCountAdmin(admin.ModelAdmin):
    list_display = ("novel", "views", "last_updated")
    search_fields = ("novel__title",)
    readonly_fields = ("last_updated",)
    raw_id_fields = ("novel",)


@admin.register(WeeklyNovelView)
class WeeklyNovelViewAdmin(admin.ModelAdmin):
    list_display = ("novel", "year_week", "views")
    list_filter = ("year_week",)
    search_fields = ("novel__title", "year_week")
    raw_id_fields = ("novel",)


@admin.register(FeaturedNovel)
class FeaturedNovelAdmin(admin.ModelAdmin):
    list_display = ("novel", "description_preview", "created_at", "updated_at")
    search_fields = ("novel__title", "description")
    raw_id_fields = ("novel",)

    def description_preview(self, obj):
        preview = obj.description[:50] + "..." if len(obj.description) > 50 else obj.description
        return preview

    description_preview.short_description = "Description"


@admin.register(NovelSimilarity)
class NovelSimilarityAdmin(admin.ModelAdmin):
    list_display = ("from_novel", "to_novel", "similarity")
    search_fields = ("from_novel__title", "to_novel__title")
    raw_id_fields = ("from_novel", "to_novel")
    readonly_fields = ("similarity",)
    fieldsets = (
        (
            "Similarity Information",
            {"fields": ("from_novel", "to_novel", "similarity")},
        ),
    )
