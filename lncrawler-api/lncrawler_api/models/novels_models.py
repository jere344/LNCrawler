from django.db import models
from django.utils.text import slugify
import uuid
import os
import json
from datetime import datetime
from django.conf import settings


class Novel(models.Model):
    """
    Main novel model that groups together different sources of the same novel
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    novel_path = models.CharField(max_length=500, null=True, blank=True)  # Path relative to settings.LNCRAWL_OUTPUT_PATH
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.title
    
    @property
    def sources_count(self):
        return self.sources.count()
    
    @property
    def total_chapters(self):
        return sum(source.chapters_count for source in self.sources.all())


class Person(models.Model):
    """Base model for people involved with novels (authors, editors, translators)"""
    name = models.CharField(max_length=255)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class Author(Person):
    """Author of a novel"""
    pass


class Editor(Person):
    """Editor of a novel"""
    pass


class Translator(Person):
    """Translator of a novel"""
    pass


class Tag(models.Model):
    """Tags for novels"""
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Genre(models.Model):
    """Genres for novels"""
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


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
    
    # People relationships (many-to-many)
    authors = models.ManyToManyField(Author, related_name='novels', blank=True)
    editors = models.ManyToManyField(Editor, related_name='novels', blank=True)
    translators = models.ManyToManyField(Translator, related_name='novels', blank=True)
    
    # Additional metadata
    language = models.CharField(max_length=100, default='en')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Unknown')
    synopsis = models.TextField(blank=True, null=True)
    
    # Categories (many-to-many)
    genres = models.ManyToManyField(Genre, related_name='novels', blank=True)
    tags = models.ManyToManyField(Tag, related_name='novels', blank=True)
    
    # Extra metadata fields that may be in the JSON
    is_rtl = models.BooleanField(default=False)
    novel_tags = models.TextField(blank=True, null=True)
    has_manga = models.BooleanField(null=True, blank=True)
    has_mtl = models.BooleanField(null=True, blank=True)
    source = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
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
                'novel_tags': novel_data.get('novel_tags'),
                'has_manga': novel_data.get('has_manga'),
                'has_mtl': novel_data.get('has_mtl'),
                'source': novel_data.get('source'),
                'description': novel_data.get('description'),
                'original_publisher': novel_data.get('original_publisher'),
                'english_publisher': novel_data.get('english_publisher'),
                'novelupdates_url': novel_data.get('novelupdates_url'),
                'meta_file_path': meta_json_path,
                'last_chapter_update': datetime.now(),
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
        
        # Handle genres (list of strings)
        genres_list = novel_data.get('genres', [])
        novel_from_source.genres.clear()
        for genre_name in genres_list:
            if genre_name:
                genre, _ = Genre.objects.get_or_create(name=genre_name)
                novel_from_source.genres.add(genre)
        
        # Handle tags (list of strings)
        tags_list = novel_data.get('tags', [])
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
        
        # Process chapters
        if 'chapters' in novel_data:
            # Get the base directory for chapter JSON files
            relative_json_dir = os.path.join(source_path, 'json')
            
            for chapter_data in novel_data['chapters']:
                chapter_id = chapter_data.get('id')
                
                # Format chapter_id with leading zeros for proper sorting
                relative_chapter_path = os.path.join(relative_json_dir, f"{chapter_id:05d}.json")
                
                # Check if the file exists
                file_exists = os.path.exists(os.path.join(output_path, relative_chapter_path))
                
                Chapter.objects.update_or_create(
                    novel_from_source=novel_from_source,
                    chapter_id=chapter_id,
                    defaults={
                        'url': chapter_data.get('url', ''),
                        'title': chapter_data.get('title', f'Chapter {chapter_id}'),
                        'volume': chapter_data.get('volume', 0),
                        'volume_title': chapter_data.get('volume_title', ''),
                        'chapter_path': relative_chapter_path if file_exists else None,
                        'images': chapter_data.get('images', {}),
                        'success': chapter_data.get('success', False) if file_exists else False,
                    }
                )
        
        return novel_from_source


class Volume(models.Model):
    """
    Represents a volume within a novel from a specific source
    """
    novel_from_source = models.ForeignKey(NovelFromSource, on_delete=models.CASCADE, related_name='volumes')
    volume_id = models.IntegerField()
    title = models.CharField(max_length=255)
    start_chapter = models.IntegerField(null=True, blank=True)
    final_chapter = models.IntegerField(null=True, blank=True)
    chapter_count = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ('novel_from_source', 'volume_id')
    
    def __str__(self):
        return f"{self.title} - {self.novel_from_source.title}"


class Chapter(models.Model):
    """
    Represents a chapter within a novel from a specific source
    """
    novel_from_source = models.ForeignKey(NovelFromSource, on_delete=models.CASCADE, related_name='chapters')
    chapter_id = models.IntegerField()
    url = models.URLField(max_length=500)
    title = models.CharField(max_length=255)
    volume = models.IntegerField(default=0)
    volume_title = models.CharField(max_length=255, blank=True, null=True)
    chapter_path = models.CharField(max_length=500, null=True, blank=True)  # Path relative to settings.LNCRAWL_OUTPUT_PATH
    images = models.JSONField(default=dict)  # Keep as JSONField due to complex structure
    success = models.BooleanField(default=False)
    
    class Meta:
        unique_together = ('novel_from_source', 'chapter_id')
        ordering = ['chapter_id']
    
    def __str__(self):
        return f"{self.title} - {self.novel_from_source.title}"
    
    @property
    def body(self):
        """Read the chapter body from the file"""
        if self.chapter_path:
            try:
                full_path = os.path.join(settings.LNCRAWL_OUTPUT_PATH, self.chapter_path)
                if os.path.exists(full_path):
                    with open(full_path, 'r', encoding='utf-8') as f:
                        chapter_data = json.load(f)
                        return chapter_data.get('body')
            except Exception as e:
                print(f"Error reading chapter file {full_path}: {e}")
        
        return None
    
    @property
    def has_content(self):
        """Check if the chapter file exists and has content"""
        if self.chapter_path:
            try:
                full_path = os.path.join(settings.LNCRAWL_OUTPUT_PATH, self.chapter_path)
                if os.path.exists(full_path):
                    with open(full_path, 'r', encoding='utf-8') as f:
                        chapter_data = json.load(f)
                        body = chapter_data.get('body')
                        return body is not None and len(body) > 0
            except Exception:
                pass
        
        return False


class SourceVote(models.Model):
    """
    Tracks upvotes and downvotes for novel sources
    """
    VOTE_CHOICES = [
        ('up', 'Upvote'),
        ('down', 'Downvote'),
    ]
    
    source = models.ForeignKey(NovelFromSource, on_delete=models.CASCADE, related_name='votes')
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