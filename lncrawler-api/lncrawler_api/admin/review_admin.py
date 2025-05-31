from django.contrib import admin
from ..models import Review, ReviewReaction


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("title", "novel", "user", "rating_display", "created_at", "reaction_count_display")
    list_filter = ("rating", "created_at", "updated_at")
    search_fields = ("title", "novel__title", "user__username", "content")
    readonly_fields = ("id", "created_at", "updated_at", "reaction_count_display")
    raw_id_fields = ("novel", "user")

    def rating_display(self, obj):
        return "★" * obj.rating

    def reaction_count_display(self, obj):
        return obj.get_reaction_count

    rating_display.short_description = "Rating"
    reaction_count_display.short_description = "Reactions"

    fieldsets = (
        (
            "Review Information",
            {"fields": (("id", "novel", "user"), ("title", "rating"), "content")},
        ),
        ("Metadata", {"fields": (("created_at", "updated_at"), "reaction_count_display")}),
    )


@admin.register(ReviewReaction)
class ReviewReactionAdmin(admin.ModelAdmin):
    list_display = ("review", "user_or_ip", "reaction_display", "created_at")
    list_filter = ("reaction", "created_at")
    search_fields = ("review__title", "user__username", "ip_address", "review__novel__title")
    readonly_fields = ("id", "created_at")
    raw_id_fields = ("review", "user")

    def reaction_display(self, obj):
        return obj.get_reaction_display()

    def user_or_ip(self, obj):
        return obj.user.username if obj.user else f"Anonymous ({obj.ip_address})"

    reaction_display.short_description = "Reaction"
    user_or_ip.short_description = "User/IP"

    fieldsets = (
        (
            "Reaction Information",
            {"fields": (("id", "review"), ("user", "ip_address"), "reaction", "created_at")},
        ),
    )
