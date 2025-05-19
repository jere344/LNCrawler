from django.contrib import admin
from django.urls import path
from django.shortcuts import render
from django.utils.html import format_html
from django.urls import reverse
from .forms import MetaJsonImportForm, MassImportForm
from .commands import handle_meta_json_import, handle_mass_import
from django.conf import settings
from ..models import (
    Job, Novel, NovelFromSource, Volume, Chapter, Author, 
    Editor, Translator, Tag, Genre, SourceVote, NovelRating,
    NovelViewCount, WeeklyNovelView, Comment, CommentVote, FeaturedNovel
)

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'query', 'created_at', 'updated_at', 'progress', 'total_items')
    list_filter = ('status', 'created_at', 'updated_at')
    search_fields = ('query', 'output_path', 'error_message', 'import_message')
    readonly_fields = ('id', 'created_at', 'updated_at', 'job_pid')
    
    fieldsets = (
        ('Job Information', {
            'fields': ('id', 'status', 'query', 'job_pid', 'created_at', 'updated_at')
        }),
        ('Progress', {
            'fields': ('progress', 'total_items')
        }),
        ('Results', {
            'fields': ('search_results', 'selected_novel', 'output_path', 'output_files', 'import_message')
        }),
        ('Error Information', {
            'fields': ('error_message',)
        }),
    )

# Register all novel-related models
@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Editor)
class EditorAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Translator)
class TranslatorAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

# Inline for showing sources in Novel admin
class NovelFromSourceInline(admin.TabularInline):
    model = NovelFromSource
    extra = 0
    fields = ('link_to_source', 'source_name', 'status', 'chapters_count', 'last_chapter_update')
    readonly_fields = ('link_to_source', 'chapters_count', 'last_chapter_update')
    show_change_link = True
    can_delete = False
    
    def link_to_source(self, obj):
        url = reverse('admin:lncrawler_api_novelfromsource_change', args=[obj.id])
        return format_html('<a href="{}">{}</a>', url, obj.title)
    
    link_to_source.short_description = 'Title'
    
# Inline for showing chapters in NovelFromSource admin
class ChapterInline(admin.TabularInline):
    model = Chapter
    extra = 0
    fields = ('chapter_id', 'link_to_chapter', 'success', 'has_content')
    readonly_fields = ('chapter_id', 'link_to_chapter', 'success', 'has_content')
    show_change_link = True
    can_delete = False
    ordering = ('chapter_id',)
    max_num = 5000  # Limit displayed chapters to avoid page load performance issues
    
    def link_to_chapter(self, obj):
        url = reverse('admin:lncrawler_api_chapter_change', args=[obj.id])
        return format_html('<a href="{}">{}</a>', url, obj.title)
    
    link_to_chapter.short_description = 'Title'

# Add inline for showing ratings in Novel admin
class NovelRatingInline(admin.TabularInline):
    model = NovelRating
    extra = 0
    fields = ('ip_address', 'rating', 'created_at')
    readonly_fields = ('ip_address', 'created_at')
    can_delete = True
    max_num = 100  # Limit displayed ratings

# Add inline for showing votes in NovelFromSource admin
class SourceVoteInline(admin.TabularInline):
    model = SourceVote
    extra = 0
    fields = ('ip_address', 'vote_type', 'created_at')
    readonly_fields = ('ip_address', 'created_at')
    can_delete = True
    max_num = 100  # Limit displayed votes

@admin.register(Novel)
class NovelAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'sources_count', 'view_count_display', 'created_at', 'updated_at')
    search_fields = ('title', 'slug')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('id', 'created_at', 'updated_at', 'sources_count', 'view_count_display')
    inlines = [NovelFromSourceInline, NovelRatingInline]
    
    def view_count_display(self, obj):
        try:
            return obj.view_count.views
        except NovelViewCount.DoesNotExist:
            return 0
    
    view_count_display.short_description = 'Views'
    
    # Add import button to the changelist page
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('import-meta-json/', self.admin_site.admin_view(self.import_meta_json), name='novel-import-meta'),
            path('mass-import/', self.admin_site.admin_view(self.mass_import), name='novel-mass-import'),
        ]
        return custom_urls + urls
    
    def import_meta_json(self, request):
        if request.method == 'POST':
            form = MetaJsonImportForm(request.POST)
            return handle_meta_json_import(self, request, form)
        else:
            form = MetaJsonImportForm()
        
        context = {
            'form': form,
            'opts': self.model._meta,
            'title': 'Import Novel from meta.json',
        }
        return render(request, 'admin/import_meta_json.html', context)

    def mass_import(self, request):
        if request.method == 'POST':
            form = MassImportForm(request.POST)
            return handle_mass_import(self, request, form)
        else:
            form = MassImportForm()
        
        context = {
            'form': form,
            'opts': self.model._meta,
            'title': 'Mass Import Novels from Directory',
            'library_path': settings.LNCRAWL_OUTPUT_PATH
        }
        return render(request, 'admin/mass_import_form.html', context)

    # Add an import button to the changelist page
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['import_button'] = {
            'url': reverse('admin:novel-import-meta'),
            'label': 'Import from meta.json'
        }
        extra_context['mass_import_button'] = {
            'url': reverse('admin:novel-mass-import'),
            'label': 'Mass Import'
        }
        return super().changelist_view(request, extra_context=extra_context)

@admin.register(NovelFromSource)
class NovelFromSourceAdmin(admin.ModelAdmin):
    list_display = ('title', 'source_name', 'link_to_novel', 'status', 'chapters_count', 'vote_score_display', 'last_chapter_update')
    list_filter = ('source_name', 'status', 'language')
    search_fields = ('title', 'novel__title', 'source_name')
    readonly_fields = ('id', 'created_at', 'updated_at', 'chapters_count', 'link_to_novel', 'upvotes', 'downvotes', 'vote_score')
    raw_id_fields = ('novel',)
    inlines = [ChapterInline, SourceVoteInline]
    
    def link_to_novel(self, obj):
        url = reverse('admin:lncrawler_api_novel_change', args=[obj.novel.id])
        return format_html('<a href="{}">{}</a>', url, obj.novel.title)
    
    link_to_novel.short_description = 'Novel'
    
    def vote_score_display(self, obj):
        return obj.vote_score
    
    vote_score_display.short_description = 'Vote Score'
    
@admin.register(Volume)
class VolumeAdmin(admin.ModelAdmin):
    list_display = ('title', 'novel_from_source', 'volume_id', 'chapter_count')
    list_filter = ('novel_from_source__source_name',)
    search_fields = ('title', 'novel_from_source__title')
    raw_id_fields = ('novel_from_source',)

@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ('title', 'link_to_novel_source', 'chapter_id', 'volume', 'success', 'has_content')
    list_filter = ('novel_from_source__source_name', 'success', 'volume')
    search_fields = ('title', 'novel_from_source__title')
    raw_id_fields = ('novel_from_source',)
    
    def link_to_novel_source(self, obj):
        url = reverse('admin:lncrawler_api_novelfromsource_change', args=[obj.novel_from_source.id])
        return format_html('<a href="{}">{}</a>', url, obj.novel_from_source.title)
    
    link_to_novel_source.short_description = 'Novel From Source'

# Register new models
@admin.register(SourceVote)
class SourceVoteAdmin(admin.ModelAdmin):
    list_display = ('source', 'ip_address', 'vote_type', 'created_at')
    list_filter = ('vote_type', 'created_at')
    search_fields = ('source__title', 'ip_address')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('source',)

@admin.register(NovelRating)
class NovelRatingAdmin(admin.ModelAdmin):
    list_display = ('novel', 'ip_address', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('novel__title', 'ip_address')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('novel',)

@admin.register(NovelViewCount)
class NovelViewCountAdmin(admin.ModelAdmin):
    list_display = ('novel', 'views', 'last_updated')
    search_fields = ('novel__title',)
    readonly_fields = ('last_updated',)
    raw_id_fields = ('novel',)

@admin.register(WeeklyNovelView)
class WeeklyNovelViewAdmin(admin.ModelAdmin):
    list_display = ('novel', 'year_week', 'views')
    list_filter = ('year_week',)
    search_fields = ('novel__title', 'year_week')
    raw_id_fields = ('novel',)

# Inline for showing comment votes in Comment admin
class CommentVoteInline(admin.TabularInline):
    model = CommentVote
    extra = 0
    fields = ('ip_address', 'vote_type', 'created_at')
    readonly_fields = ('ip_address', 'created_at')
    can_delete = True
    max_num = 100  # Limit displayed votes

# Inline for showing replies in Comment admin
class CommentReplyInline(admin.TabularInline):
    model = Comment
    extra = 0
    fields = ('author_name', 'message', 'contains_spoiler', 'created_at', 'vote_score')
    readonly_fields = ('created_at', 'vote_score')
    can_delete = True
    verbose_name = "Reply"
    verbose_name_plural = "Replies"
    fk_name = 'parent'  # Specify which foreign key to use
    
    def vote_score(self, obj):
        return obj.vote_score
    
    vote_score.short_description = 'Vote Score'

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('author_name', 'target_display', 'message_preview', 'contains_spoiler', 'created_at', 'vote_score_display', 'reply_count')
    list_filter = ('contains_spoiler', 'created_at')
    search_fields = ('author_name', 'message', 'novel__title', 'chapter__title')
    readonly_fields = ('id', 'created_at', 'vote_score_display', 'parent_comment', 'target_link')
    raw_id_fields = ('novel', 'chapter', 'parent')
    fieldsets = (
        ('Comment Information', {
            'fields': ('id', 'author_name', 'target_link', 'parent_comment', 'contains_spoiler', 'created_at')
        }),
        ('Content', {
            'fields': ('message',)
        }),
        ('Votes', {
            'fields': ('upvotes', 'downvotes', 'vote_score_display')
        }),
        ('Source', {
            'fields': ('ip_address',)
        }),
    )
    inlines = [CommentReplyInline, CommentVoteInline]
    
    def message_preview(self, obj):
        # Truncate long messages for display in the list
        preview = obj.message[:50] + '...' if len(obj.message) > 50 else obj.message
        return preview
    
    message_preview.short_description = 'Message'
    
    def vote_score_display(self, obj):
        return obj.vote_score
    
    vote_score_display.short_description = 'Vote Score'
    
    def reply_count(self, obj):
        return obj.replies.count()
    
    reply_count.short_description = 'Replies'
    
    def target_display(self, obj):
        if obj.novel:
            return f"Novel: {obj.novel.title}"
        elif obj.chapter:
            return f"Chapter: {obj.chapter.title}"
        return "Unknown"
    
    target_display.short_description = 'Target'
    
    def parent_comment(self, obj):
        if obj.parent:
            url = reverse('admin:lncrawler_api_comment_change', args=[obj.parent.id])
            return format_html('<a href="{}">{}</a>', url, f"Reply to: {obj.parent.author_name}")
        return "Top-level comment"
    
    parent_comment.short_description = 'Parent Comment'
    
    def target_link(self, obj):
        if obj.novel:
            url = reverse('admin:lncrawler_api_novel_change', args=[obj.novel.id])
            return format_html('<a href="{}">{}</a>', url, obj.novel.title)
        elif obj.chapter:
            url = reverse('admin:lncrawler_api_chapter_change', args=[obj.chapter.id])
            return format_html('<a href="{}">{}</a>', url, obj.chapter.title)
        return "Unknown"
    
    target_link.short_description = 'Target'

@admin.register(CommentVote)
class CommentVoteAdmin(admin.ModelAdmin):
    list_display = ('comment_preview', 'ip_address', 'vote_type', 'created_at')
    list_filter = ('vote_type', 'created_at')
    search_fields = ('comment__message', 'comment__author_name', 'ip_address')
    readonly_fields = ('created_at', 'updated_at', 'comment_link')
    raw_id_fields = ('comment',)
    
    def comment_preview(self, obj):
        preview = obj.comment.message[:30] + '...' if len(obj.comment.message) > 30 else obj.comment.message
        return f"{obj.comment.author_name}: {preview}"
    
    comment_preview.short_description = 'Comment'
    
    def comment_link(self, obj):
        url = reverse('admin:lncrawler_api_comment_change', args=[obj.comment.id])
        return format_html('<a href="{}">{}</a>', url, f"Comment by {obj.comment.author_name}")
    
    comment_link.short_description = 'Comment'

@admin.register(FeaturedNovel)
class FeaturedNovelAdmin(admin.ModelAdmin):
    list_display = ('novel', 'description_preview', 'created_at', 'updated_at')
    search_fields = ('novel__title', 'description')
    raw_id_fields = ('novel',)
    
    def description_preview(self, obj):
        preview = obj.description[:50] + '...' if len(obj.description) > 50 else obj.description
        return preview
    
    description_preview.short_description = 'Description'