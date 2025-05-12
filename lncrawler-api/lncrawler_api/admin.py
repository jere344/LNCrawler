from django.contrib import admin
from django.urls import path
from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django import forms
from django.utils.html import format_html
import os
import glob
import shutil
from django.conf import settings
import logging

# Register your models here.

from django.contrib import admin
from .models import Job, Novel, NovelFromSource, Volume, Chapter, Author, Editor, Translator, Tag, Genre

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

# Custom form for meta.json file path input
class MetaJsonImportForm(forms.Form):
    meta_json_path = forms.CharField(
        label='Path to meta.json file',
        max_length=500,
        help_text='Enter the full path to a meta.json file (e.g., C:\\Users\\Jeremy\\novels\\novel_name\\meta.json)'
    )

# Custom form for mass import directory path
class MassImportForm(forms.Form):
    IMPORT_ACTIONS = [
        ('import_only', 'Import Only (No File Operations)'),
        ('copy', 'Copy to Library Path and Import'),
        ('move', 'Move to Library Path and Import')
    ]
    
    root_directory = forms.CharField(
        label='Root Directory Path',
        max_length=500,
        help_text='Enter the full path to a directory to recursively search for meta.json files (e.g., C:\\Users\\Jeremy\\novels)'
    )
    
    import_action = forms.ChoiceField(
        label='Import Action',
        choices=IMPORT_ACTIONS,
        initial='import_only',
        help_text='Select whether to just import, or copy/move files to library path before importing'
    )

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

@admin.register(Novel)
class NovelAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'sources_count', 'total_chapters', 'created_at', 'updated_at')
    search_fields = ('title', 'slug')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('id', 'created_at', 'updated_at', 'sources_count', 'total_chapters')
    inlines = [NovelFromSourceInline]
    
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
            if form.is_valid():
                meta_json_path = form.cleaned_data['meta_json_path']
                
                try:
                    # Verify the file exists
                    import os
                    if not os.path.isfile(meta_json_path):
                        raise ValueError(f"File not found: {meta_json_path}")
                    
                    # Use the model method to process the meta.json file
                    novel_from_source = NovelFromSource.from_meta_json(meta_json_path)
                    
                    self.message_user(
                        request,
                        f"Successfully imported '{novel_from_source.title}' from {novel_from_source.source_name}"
                    )
                    
                except Exception as e:
                    self.message_user(
                        request,
                        f"Error importing meta.json file: {str(e)}",
                        level='ERROR'
                    )
                        
                return HttpResponseRedirect(reverse('admin:lncrawler_api_novel_changelist'))
                
        else:
            form = MetaJsonImportForm()
        
        context = {
            'form': form,
            'opts': self.model._meta,
            'title': 'Import Novel from meta.json',
        }
        return render(request, 'admin/import_meta_json.html', context)

    def mass_import(self, request):
        """View for mass importing meta.json files from a directory recursively"""
        import_results = {
            'successful': [],
            'failed': [],
            'file_operations': []
        }
        
        logger = logging.getLogger('lncrawler_api')
        
        if request.method == 'POST':
            form = MassImportForm(request.POST)
            if form.is_valid():
                root_directory = form.cleaned_data['root_directory']
                import_action = form.cleaned_data['import_action']
                
                try:
                    # Check if directory exists
                    if not os.path.isdir(root_directory):
                        raise ValueError(f"Directory not found: {root_directory}")
                    
                    # Recursively find all meta.json files
                    meta_files = glob.glob(os.path.join(root_directory, '**/meta.json'), recursive=True)
                    
                    # Process each meta.json file
                    for meta_file_path in meta_files:
                        try:
                            # Get source_folder and novel_folder from meta_file_path
                            source_folder = os.path.dirname(meta_file_path)
                            source_folder_name = os.path.basename(source_folder)
                            
                            # Try to determine novel_folder_name from parent directory 
                            # (assuming directory structure is novel_folder/source_folder/meta.json)
                            novel_folder_name = os.path.basename(os.path.dirname(source_folder))
                            
                            # If import action is copy or move
                            if import_action in ('copy', 'move'):
                                # Ensure the target directory exists in the library path
                                library_novel_path = os.path.join(settings.LNCRAWL_OUTPUT_PATH, novel_folder_name)
                                os.makedirs(library_novel_path, exist_ok=True)
                                
                                # Target path for the source folder
                                target_source_path = os.path.join(library_novel_path, source_folder_name)
                                
                                # Check if the target directory already exists
                                if os.path.exists(target_source_path):
                                    logger.warning(f"Target directory already exists: {target_source_path}")
                                    import_results['file_operations'].append({
                                        'source': source_folder,
                                        'target': target_source_path,
                                        'action': import_action,
                                        'status': 'skipped',
                                        'reason': 'Target already exists'
                                    })
                                else:
                                    # Copy or move the directory
                                    if import_action == 'copy':
                                        shutil.copytree(source_folder, target_source_path)
                                        logger.info(f"Copied {source_folder} to {target_source_path}")
                                    else:  # move
                                        shutil.move(source_folder, target_source_path)
                                        logger.info(f"Moved {source_folder} to {target_source_path}")
                                    
                                    import_results['file_operations'].append({
                                        'source': source_folder,
                                        'target': target_source_path,
                                        'action': import_action,
                                        'status': 'success'
                                    })
                                    
                                    # Update the meta_file_path to point to the new location
                                    meta_file_path = os.path.join(target_source_path, 'meta.json')
                            
                            # Now import the meta.json file
                            novel_from_source = NovelFromSource.from_meta_json(meta_file_path)
                            
                            import_results['successful'].append({
                                'path': meta_file_path,
                                'title': novel_from_source.title,
                                'source': novel_from_source.source_name
                            })
                        except Exception as e:
                            logger.error(f"Error importing {meta_file_path}: {str(e)}")
                            import_results['failed'].append({
                                'path': meta_file_path,
                                'error': str(e)
                            })
                    
                    # Return results to the template
                    self.message_user(
                        request,
                        f"Import completed: {len(import_results['successful'])} successful, {len(import_results['failed'])} failed"
                    )
                    
                    context = {
                        'form': form,
                        'opts': self.model._meta,
                        'title': 'Mass Import Results',
                        'results': import_results,
                        'total_found': len(meta_files),
                        'import_action': import_action
                    }
                    return render(request, 'admin/mass_import_results.html', context)
                    
                except Exception as e:
                    logger.exception(f"Error during mass import: {str(e)}")
                    self.message_user(
                        request,
                        f"Error during mass import: {str(e)}",
                        level='ERROR'
                    )
                    return HttpResponseRedirect(reverse('admin:lncrawler_api_novel_changelist'))
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
    list_display = ('title', 'source_name', 'link_to_novel', 'status', 'chapters_count', 'last_chapter_update')
    list_filter = ('source_name', 'status', 'language')
    search_fields = ('title', 'novel__title', 'source_name')
    readonly_fields = ('id', 'created_at', 'updated_at', 'chapters_count', 'link_to_novel')
    raw_id_fields = ('novel',)
    inlines = [ChapterInline]
    
    def link_to_novel(self, obj):
        url = reverse('admin:lncrawler_api_novel_change', args=[obj.novel.id])
        return format_html('<a href="{}">{}</a>', url, obj.novel.title)
    
    link_to_novel.short_description = 'Novel'

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