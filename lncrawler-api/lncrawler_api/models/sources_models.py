from django.db import models
import uuid
import os
import json
import shutil
from django.conf import settings
from django.utils.text import slugify
from django.utils import timezone

from .novels_models import Novel, Author, Editor, Translator, Tag
from .chapter_models import Volume, Chapter
from ..utils.chapter_utils import check_chapter_path_has_content


class NovelFromSource(models.Model):
    """
    Represents a novel from a specific source with its metadata
    Maps directly to the structure found in meta.json files
    """
    STATUS_CHOICES = [
        ('Ongoing', 'Ongoing'),
        ('Completed', 'Completed'),
        ('Unknown', 'Unknown'),
        ('On Hiatus', 'On Hiatus'),
        ('Cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='sources')
    
    # Basic metadata
    title = models.CharField(max_length=255)
    source_url = models.URLField(max_length=500)
    source_name = models.CharField(max_length=100)
    source_slug = models.SlugField(max_length=100, blank=True)
    cover_url = models.URLField(max_length=500, null=True, blank=True)
    
    # Path information relative to settings.LNCRAWL_OUTPUT_PATH
    source_path = models.CharField(max_length=500, null=True, blank=True)
    cover_path = models.CharField(max_length=500, null=True, blank=True)
    overview_picture_path = models.CharField(max_length=500, null=True, blank=True) 
    
    # People relationships (many-to-many)
    authors = models.ManyToManyField(Author, related_name='novels', blank=True)
    editors = models.ManyToManyField(Editor, related_name='novels', blank=True)
    translators = models.ManyToManyField(Translator, related_name='novels', blank=True)
    
    # Additional metadata
    language = models.CharField(max_length=100, default='en')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Unknown')
    synopsis = models.TextField(blank=True, null=True)
    
    # Categories (many-to-many)
    tags = models.ManyToManyField(Tag, related_name='novels', blank=True)
    
    # Extra metadata fields that may be in the JSON
    is_rtl = models.BooleanField(default=False)
    has_manga = models.BooleanField(null=True, blank=True)
    has_mtl = models.BooleanField(null=True, blank=True)
    original_publisher = models.CharField(max_length=255, null=True, blank=True)
    english_publisher = models.CharField(max_length=255, null=True, blank=True)
    novelupdates_url = models.URLField(max_length=500, null=True, blank=True)
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_chapter_update = models.DateTimeField(null=True, blank=True)
    
    # File paths
    meta_file_path = models.CharField(max_length=500, null=True, blank=True)
    
    # Voting fields
    upvotes = models.IntegerField(default=0)
    downvotes = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ('novel', 'source_url')
    
    def __str__(self):
        return f"{self.title} ({self.source_name})"

    @property
    def chapters_count(self):
        return self.chapters.count()
    
    @property
    def volumes_count(self):
        return self.volumes.count()
    
    @property
    def vote_score(self):
        return self.upvotes - self.downvotes
    
    @classmethod
    def from_meta_json(cls, meta_json_path):
        """
        Create a NovelFromSource instance from a meta.json file
        """
        with open(meta_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        novel_data = data.get('novel', {})
        
        # Get the title from the meta.json file
        title = novel_data.get('title', '')
        if not title:
            raise ValueError("The meta.json file does not contain a novel title")
        
        # Determine paths relative to settings.LNCRAWL_OUTPUT_PATH
        source_dir = os.path.dirname(meta_json_path)  # Directory containing meta.json
        novel_dir = os.path.dirname(source_dir)       # Parent directory of source_dir
        
        # Make paths relative to settings.LNCRAWL_OUTPUT_PATH
        output_path = settings.LNCRAWL_OUTPUT_PATH
        if not output_path.endswith(os.path.sep):
            output_path += os.path.sep
            
        novel_path = os.path.relpath(novel_dir, output_path)
        source_path = os.path.relpath(source_dir, output_path)
        cover_path = os.path.join(source_path, 'cover.jpg')
        
        # Create or get novel based on the novel_path
        novel_slug = slugify(os.path.basename(novel_path))
        novel, created = Novel.objects.get_or_create(
            slug=novel_slug,
            defaults={
                'title': title,
                'novel_path': novel_path
            }
        )
        
        # Create or update the NovelFromSource
        source_url = novel_data.get('url', '')
        source_name = os.path.basename(source_dir)
        source_slug = slugify(source_name)
        
        novel_from_source, created = cls.objects.update_or_create(
            novel=novel,
            source_url=source_url,
            defaults={
                'title': title,
                'source_name': source_name,
                'source_slug': source_slug,
                'source_path': source_path,
                'cover_path': cover_path if os.path.exists(os.path.join(output_path, cover_path)) else None,
                'cover_url': novel_data.get('cover_url'),
                'language': novel_data.get('language', 'en'),
                'status': novel_data.get('status', 'Unknown'),
                'synopsis': novel_data.get('synopsis', ''),
                'is_rtl': novel_data.get('is_rtl', False),
                'has_manga': novel_data.get('has_manga'),
                'has_mtl': novel_data.get('has_mtl'),
                'original_publisher': novel_data.get('original_publisher'),
                'english_publisher': novel_data.get('english_publisher'),
                'novelupdates_url': novel_data.get('novelupdates_url'),
                'meta_file_path': meta_json_path,
                'last_chapter_update': timezone.now(),
            }
        )
        
        # Handle authors (list of strings)
        authors_list = novel_data.get('authors', [])
        novel_from_source.authors.clear()
        for author_name in authors_list:
            if author_name:
                author, _ = Author.objects.get_or_create(name=author_name)
                novel_from_source.authors.add(author)
        
        # Handle editors (list of strings)
        editors_list = novel_data.get('editors', [])
        novel_from_source.editors.clear()
        for editor_name in editors_list:
            if editor_name:
                editor, _ = Editor.objects.get_or_create(name=editor_name)
                novel_from_source.editors.add(editor)
        
        # Handle translators (list of strings)
        translators_list = novel_data.get('translators', [])
        novel_from_source.translators.clear()
        for translator_name in translators_list:
            if translator_name:
                translator, _ = Translator.objects.get_or_create(name=translator_name)
                novel_from_source.translators.add(translator)
        
        # Handle tags (either list of string or comma-separated string)
        if isinstance(novel_data.get('novel_tags'), str):
            tags_list = [tag.strip() for tag in novel_data['novel_tags'].split(',')]
        else:
            tags_list = novel_data.get('novel_tags', [])
        novel_from_source.tags.clear()
        for tag_name in tags_list:
            if tag_name:
                tag, _ = Tag.objects.get_or_create(name=tag_name)
                novel_from_source.tags.add(tag)
        
        # Process volumes if they exist
        if 'volumes' in novel_data:
            for volume_data in novel_data['volumes']:
                Volume.objects.update_or_create(
                    novel_from_source=novel_from_source,
                    volume_id=volume_data.get('id'),
                    defaults={
                        'title': volume_data.get('title', f'Volume {volume_data.get("id")}'),
                        'start_chapter': volume_data.get('start_chapter'),
                        'final_chapter': volume_data.get('final_chapter'),
                        'chapter_count': volume_data.get('chapter_count', 0),
                    }
                )
        
        # Process chapters - using bulk create/update for better performance
        if 'chapters' in novel_data:
            # Get the base directory for chapter JSON files
            relative_json_dir = os.path.join(source_path, 'json')
            
            # Get existing chapters for this source to avoid duplicates
            existing_chapters = {
                ch.chapter_id: ch for ch in Chapter.objects.filter(novel_from_source=novel_from_source)
            }
            
            new_chapters = []
            chapters_to_update = []
            
            for chapter_data in novel_data['chapters']:
                chapter_id = chapter_data.get('id')
                
                # Format chapter_id with leading zeros for proper sorting
                relative_chapter_path = os.path.join(relative_json_dir, f"{chapter_id:05d}.json")
                
                # Check if the file exists
                file_exists = os.path.exists(os.path.join(settings.LNCRAWL_OUTPUT_PATH, relative_chapter_path))
                
                # Extract only the image filenames (keys) from the images dictionary
                images_dict = chapter_data.get('images', {})
                image_filenames = list(images_dict.keys()) if images_dict else []
    
                # Prepare chapter data
                chapter_dict = {
                    'url': chapter_data.get('url', ''),
                    'title': chapter_data.get('title', f'Chapter {chapter_id}'),
                    'volume': chapter_data.get('volume', 0),
                    'volume_title': chapter_data.get('volume_title', ''),
                    'chapter_path': relative_chapter_path if file_exists else None,
                    'images': image_filenames,
                    'has_content': check_chapter_path_has_content(relative_chapter_path) if file_exists else False,
                }
                
                # If chapter exists, update it, otherwise create new
                if chapter_id in existing_chapters:
                    chapter = existing_chapters[chapter_id]
                    for key, value in chapter_dict.items():
                        setattr(chapter, key, value)
                    chapters_to_update.append(chapter)
                else:
                    new_chapters.append(Chapter(
                        novel_from_source=novel_from_source,
                        chapter_id=chapter_id,
                        **chapter_dict
                    ))
            
            # Bulk create new chapters
            if new_chapters:
                Chapter.objects.bulk_create(new_chapters)
            
            # Bulk update existing chapters
            if chapters_to_update:
                fields_to_update = ['url', 'title', 'volume', 'volume_title', 'chapter_path', 'images', 'has_content']
                Chapter.objects.bulk_update(chapters_to_update, fields_to_update)
            
            # Update last_chapter_update timestamp
            novel_from_source.last_chapter_update = timezone.now()
            novel_from_source.save(update_fields=['last_chapter_update'])
        
        # Generate overview image
        novel_from_source.generate_overview_image()
        
        return novel_from_source

    def generate_overview_image(self):
        """
        Generate an overview image for this novel source
        """
        try:
            # Use dynamic import to avoid circular dependency
            from ..management.commands.generate_overview import Command as GenerateOverviewCommand
            overview_generator = GenerateOverviewCommand()
            overview_generator.generate_overview(self)
            return True
        except Exception as e:
            print(f"Error generating overview image for {self.title}: {e}")
            return False

    def delete(self, *args, **kwargs):
        """
        Override the delete method to also remove the source folder
        """
        # Check if we have a source path and it exists
        print(f"Deleting source folder: {self.source_path}")
        if self.source_path:
            full_source_path = os.path.join(settings.LNCRAWL_OUTPUT_PATH, self.source_path)
            if os.path.exists(full_source_path) and os.path.isdir(full_source_path):
                try:
                    # Delete the source folder and all its contents
                    shutil.rmtree(full_source_path)
                except Exception as e:
                    print(f"Error deleting source folder {full_source_path}: {e}")
        
        # Call the parent delete method to delete the database record
        super().delete(*args, **kwargs)


class SourceVote(models.Model):
    """
    Tracks upvotes and downvotes for novel sources
    """
    VOTE_CHOICES = [
        ('up', 'Upvote'),
        ('down', 'Downvote'),
    ]
    
    source = models.ForeignKey('NovelFromSource', on_delete=models.CASCADE, related_name='votes')
    ip_address = models.GenericIPAddressField()
    vote_type = models.CharField(max_length=4, choices=VOTE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('source', 'ip_address')
        
    def __str__(self):
        return f"{self.get_vote_type_display()} for {self.source.title} by {self.ip_address}"
    
    def save(self, *args, **kwargs):
        # Check if this is an update to an existing vote
        is_update = self.pk is not None
        old_vote_type = None
        
        if is_update:
            old_vote = SourceVote.objects.get(pk=self.pk)
            old_vote_type = old_vote.vote_type
        
        # Save the vote
        super().save(*args, **kwargs)
        
        # Update the vote counts on the source
        source = self.source
        
        # If this is a new vote
        if not is_update:
            if self.vote_type == 'up':
                source.upvotes += 1
            else:
                source.downvotes += 1
        # If this is updating an existing vote
        elif old_vote_type != self.vote_type:
            if self.vote_type == 'up':
                source.upvotes += 1
                source.downvotes -= 1
            else:
                source.downvotes += 1
                source.upvotes -= 1
        
        source.save(update_fields=['upvotes', 'downvotes'])
