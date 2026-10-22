from django.contrib import admin

from ..models import AuthorAlias


@admin.register(AuthorAlias)
class AuthorAliasAdmin(admin.ModelAdmin):
    list_display = ("name", "author", "created_at")
    search_fields = ("name", "author__name")
    raw_id_fields = ("author",)
