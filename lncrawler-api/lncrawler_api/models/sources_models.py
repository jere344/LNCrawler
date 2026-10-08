from django.db import models, transaction
import os
import re
import json
import shutil
from django.conf import settings
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db.models.functions import Upper
from django.utils.text import slugify
from django.utils import timezone

from .novels_models import Novel, NovelAlias, Author, Editor, Translator, Tag, AlternativeTitle
from .chapter_models import Volume, Chapter
from ..utils import chapter_utils, lncrawler_paths

def truncate(value, max_length=500):
    if value and len(value) > max_length:
        return value[:max_length]
    return value


def resolve_output_path(*relative):
    """
    Resolve DB-relative path parts under ``LNCRAWL_OUTPUT_PATH`` and return the
    absolute path, or ``None`` if the result escapes the output root (e.g. a
    poisoned ``..`` segment). Valid paths are returned unchanged.
    """
    base = os.path.realpath(settings.LNCRAWL_OUTPUT_PATH)
    target = os.path.realpath(os.path.join(base, *relative))
    try:
        if os.path.commonpath([base, target]) != base:
            return None
    except ValueError:
        return None
    return target

class ExternalSource(models.Model):
    """
    Represents an external source (website) where novels are crawled from
    """
    STATUS_CHOICES = [
        ('alive', 'Alive'),
        ('dead', 'Dead'),
    ]
    
    source_name = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='alive')
    
    class Meta:
        ordering = ['source_name']
    
    def __str__(self):
        return f"{self.source_name} ({self.get_status_display()})"


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

    id = models.BigAutoField(primary_key=True)
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='sources')
    
    # Basic metadata
    title = models.CharField(max_length=500)
    source_url = models.CharField(max_length=500)
    external_source = models.ForeignKey(ExternalSource, on_delete=models.CASCADE, related_name='novels')
    source_slug = models.SlugField(max_length=100, blank=True)
    cover_url = models.CharField(max_length=500, null=True, blank=True)
    
    # Path information relative to settings.LNCRAWL_OUTPUT_PATH
    source_path = models.CharField(max_length=500, null=True, blank=True)
    cover_path = models.CharField(max_length=500, null=True, blank=True)
    cover_min_path = models.CharField(max_length=500, null=True, blank=True)
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
    alternative_titles = models.ManyToManyField(AlternativeTitle, related_name='novels', blank=True)
    
    # Extra metadata fields that may be in the JSON
    is_adult = models.BooleanField(default=False)
    original_publisher = models.CharField(max_length=500, null=True, blank=True)
    english_publisher = models.CharField(max_length=500, null=True, blank=True)
    novelupdates_url = models.URLField(max_length=500, null=True, blank=True)
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_chapter_update = models.DateTimeField(null=True, blank=True)

    # All-time view count for this source. A rebuildable projection of
    # WeeklySourceView rows (incremented alongside the daily bucket on read),
    # kept as a column so lifetime totals are O(1) to read instead of a full
    # aggregation over the event table.
    total_views = models.BigIntegerField(default=0)

    # File paths
    meta_file_path = models.CharField(max_length=500, null=True, blank=True)
    
    # Voting fields
    upvotes = models.IntegerField(default=0)
    downvotes = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ('novel', 'source_url')
        indexes = [
            models.Index(fields=['-last_chapter_update'], name='nfs_last_chapter_upd_idx'),
            models.Index(fields=['language'], name='nfs_language_idx'),
            models.Index(fields=['-total_views'], name='nfs_total_views_idx'),
            GinIndex(OpClass(Upper('synopsis'), name='gin_trgm_ops'), name='nfs_synopsis_trgm_idx'),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.external_source.source_name})"

    @property
    def chapters_count(self):
        return self.chapters.count()
    
    @property
    def absolute_source_path(self):
        """
        Returns the absolute path to the source directory
        """
        if self.source_path:
            return resolve_output_path(self.source_path)
        return None
    
    @property
    def volumes_count(self):
        return self.volumes.count()
    
    @property
    def vote_score(self):
        return self.upvotes - self.downvotes
    
    @staticmethod
    def _consolidate_source_directory(source_dir, output_path, novel, existing_source):
        """
        Return the canonical ``(source_dir, source_path, meta_json_path,
        cover_path)`` for a source, relocating its files when needed.

        Destination preference:
          1. where the existing ``NovelFromSource`` row already lives, so
             updates stay anchored to the canonical folder,
          2. the canonical novel folder plus the source folder name, used for a
             brand-new source whose old folder name was merged away.
        """
        target_abs = None
        if existing_source is not None and existing_source.source_path:
            target_abs = os.path.join(output_path, existing_source.source_path)
        else:
            # ``slug`` is the folder identity ``from_meta_json`` derives, so use
            # it when ``novel_path`` was never recorded.
            canonical_dir = novel.novel_path or novel.slug
            if canonical_dir:
                target_abs = os.path.join(
                    output_path, canonical_dir, os.path.basename(source_dir)
                )

        old_novel_dir = os.path.dirname(source_dir)
        if target_abs and os.path.abspath(target_abs) != os.path.abspath(source_dir):
            lncrawler_paths.move_and_merge_directory(source_dir, target_abs)
            source_dir = target_abs
            # Remove the old novel folder if this was its only source.
            lncrawler_paths.remove_empty_directory(old_novel_dir)

        source_path = os.path.relpath(source_dir, settings.LNCRAWL_OUTPUT_PATH)
        meta_json_path = os.path.join(source_dir, 'meta.json')
        cover_path = os.path.join(source_path, 'cover.jpg')
        return source_dir, source_path, meta_json_path, cover_path

    @classmethod
    def from_meta_json(cls, meta_json_path):
        """
        Create a NovelFromSource instance from a meta.json file
        """
        with open(meta_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        novel_data = data.get('novel', {})
        # meta.json is written throughout a crawl; only the completed write has
        # accurate per-chapter success values (see resolve_chapter_has_content).
        completed = bool(data.get('session', {}).get('completed', False))
        
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
        
        # Resolve the canonical novel. An alias (created when a duplicate was
        # merged) wins over the folder-derived slug, so crawling an old name
        # reattaches to the surviving novel instead of recreating a duplicate.
        novel_slug = slugify(os.path.basename(novel_path))
        alias = NovelAlias.objects.filter(slug=novel_slug).select_related('novel').first()
        if alias is not None:
            novel = alias.novel
        else:
            novel, created = Novel.objects.get_or_create(
                slug=novel_slug,
                defaults={
                    'title': title,
                    'novel_path': novel_path
                }
            )
        
        # Create or get the external source
        source_name = os.path.basename(source_dir)
        external_source, created = ExternalSource.objects.get_or_create(
            source_name=source_name
        )
        
        # Create or update the NovelFromSource.
        # Identity is the canonical external source, not the exact URL, so the
        # same novel fetched from a mirror domain updates the existing row
        # instead of creating a duplicate.
        source_url = truncate(novel_data.get('url', ''))
        source_slug = slugify(source_name)

        novel_from_source = cls.objects.filter(novel=novel, external_source=external_source).first()
        if novel_from_source is None:
            novel_from_source = cls.objects.filter(novel=novel, source_url=source_url).first()
        existing_source = novel_from_source
        if novel_from_source is None:
            novel_from_source = cls(novel=novel)
        else:
            # Drop a legacy duplicate alias row that would violate (novel, source_url).
            cls.objects.filter(novel=novel, source_url=source_url).exclude(pk=novel_from_source.pk).delete()

        # Store files under the canonical novel folder (and keep an update in
        # the folder it already lives in).
        source_dir, source_path, meta_json_path, cover_path = cls._consolidate_source_directory(
            source_dir=source_dir,
            output_path=output_path,
            novel=novel,
            existing_source=existing_source,
        )

        novel_from_source.novel = novel
        novel_from_source.source_url = source_url
        novel_from_source.external_source = external_source
        novel_from_source.title = truncate(title)
        novel_from_source.source_slug = truncate(source_slug, 100)
        novel_from_source.source_path = truncate(source_path)
        novel_from_source.cover_path = truncate(cover_path) if cover_path else None
        novel_from_source.cover_url = truncate(novel_data.get('cover_url', ''))
        novel_from_source.language = novel_data.get('language', 'en')
        novel_from_source.status = novel_data.get('status', 'Unknown')
        novel_from_source.synopsis = novel_data.get('synopsis', '')
        novel_from_source.is_adult = bool(novel_data.get('is_adult', False))
        novel_from_source.original_publisher = truncate(novel_data.get('original_publisher', ''))
        novel_from_source.english_publisher = truncate(novel_data.get('english_publisher', ''))
        novel_from_source.novelupdates_url = truncate(novel_data.get('novelupdates_url', ''))
        novel_from_source.meta_file_path = meta_json_path
        novel_from_source.last_chapter_update = timezone.now()
        novel_from_source.save()
        
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
                novel_from_source.tags.add(Tag.resolve(tag_name))
        
        # Handle alternative titles (list of strings, tolerating a split string)
        alt_titles = novel_data.get('alternative_titles', [])
        if isinstance(alt_titles, str):
            alt_titles = [alt.strip() for alt in re.split(r'[\n;]+', alt_titles)]
        novel_from_source.alternative_titles.clear()
        for alt_title in alt_titles:
            if alt_title:
                alt, _ = AlternativeTitle.objects.get_or_create(name=truncate(alt_title))
                novel_from_source.alternative_titles.add(alt)
        
        # Process volumes if they exist
        if 'volumes' in novel_data:
            for volume_data in novel_data['volumes']:
                Volume.objects.update_or_create(
                    novel_from_source=novel_from_source,
                    volume_id=volume_data.get('id'),
                    defaults={
                        'title': truncate(volume_data.get('title', f'Volume {volume_data.get("id")}')),
                        'start_chapter': volume_data.get('start_chapter'),
                        'final_chapter': volume_data.get('final_chapter'),
                        'chapter_count': volume_data.get('chapter_count', 0),
                    }
                )
        
        # Process chapters - using bulk create/update for better performance
        if 'chapters' in novel_data:
            # Match an existing chapter by its stable url first (so a re-import
            # updates the same row even if its chapter_id moved), then by id.
            existing_list = list(
                Chapter.objects.filter(novel_from_source=novel_from_source)
            )
            existing_by_url = {ch.url: ch for ch in existing_list if ch.url}
            existing_by_id = {ch.chapter_id: ch for ch in existing_list}
            original_ids = {ch.pk: ch.chapter_id for ch in existing_list}

            new_chapters = []
            chapters_to_update = []
            used_pks = set()
            assigned_ids = set()

            for chapter_data in novel_data['chapters']:
                chapter_id = chapter_data.get('id')
                # meta.json can list the same id twice; the unique
                # (novel_from_source, chapter_id) key only allows one row.
                if chapter_id in assigned_ids:
                    continue
                assigned_ids.add(chapter_id)

                # Accept both shapes meta.json uses: a dict of filename -> {..}
                # and a plain list of filenames.
                images_data = chapter_data.get('images')
                if isinstance(images_data, dict):
                    image_filenames = list(images_data.keys())
                elif isinstance(images_data, list):
                    image_filenames = list(images_data)
                else:
                    image_filenames = []

                # Prepare chapter data
                chapter_dict = {
                    'url': truncate(chapter_data.get('url') or ''),
                    'title': truncate(chapter_data.get('title', f'Chapter {chapter_id}')),
                    'volume': chapter_data.get('volume', 0),
                    'volume_title': truncate(chapter_data.get('volume_title', '')),
                    'images': image_filenames,
                    'has_content': chapter_utils.resolve_chapter_has_content(
                        chapter_data, source_dir, chapter_id, completed=completed
                    )
                }

                existing = None
                url = chapter_dict['url']
                if url:
                    candidate = existing_by_url.get(url)
                    if candidate is not None and candidate.pk not in used_pks:
                        existing = candidate
                if existing is None:
                    candidate = existing_by_id.get(chapter_id)
                    if candidate is not None and candidate.pk not in used_pks:
                        existing = candidate

                if existing is not None:
                    used_pks.add(existing.pk)
                    existing.chapter_id = chapter_id
                    for key, value in chapter_dict.items():
                        setattr(existing, key, value)
                    chapters_to_update.append(existing)
                else:
                    new_chapters.append(Chapter(
                        novel_from_source=novel_from_source,
                        chapter_id=chapter_id,
                        **chapter_dict
                    ))

            # A re-import can renumber chapters, so rows matched by url may move
            # to a different chapter_id. A bulk UPDATE applies row by row and
            # would trip the unique (novel_from_source, chapter_id) constraint
            # while an id is still held, so reassigned rows are parked on a
            # temporary id first. Rows whose id an incoming chapter now claims
            # but that were not matched are stale and must go.
            reassigned = [
                (ch, ch.chapter_id)
                for ch in chapters_to_update
                if original_ids.get(ch.pk) != ch.chapter_id
            ]
            target_ids = {ch.chapter_id for ch in chapters_to_update} | {
                ch.chapter_id for ch in new_chapters
            }
            stale = [
                ch for ch in existing_list
                if ch.pk not in used_pks and ch.chapter_id in target_ids
            ]

            with transaction.atomic():
                if stale:
                    # An incoming chapter took these rows' slot, so they must go.
                    # Repoint their user data onto the chapter now holding that
                    # slot first: Comment.chapter is CASCADE and
                    # ReadingHistory.last_read_chapter is SET_NULL, so deleting
                    # first would silently drop comments and wipe user progress.
                    from .comments_models import Comment
                    from .users_models import ReadingHistory

                    incoming_by_id = {ch.chapter_id: ch for ch in chapters_to_update}
                    for old in stale:
                        target = incoming_by_id.get(old.chapter_id)
                        if target is None:
                            continue
                        Comment.objects.filter(chapter=old).update(chapter=target)
                        ReadingHistory.objects.filter(last_read_chapter=old).update(
                            last_read_chapter=target
                        )
                    Chapter.objects.filter(pk__in=[ch.pk for ch in stale]).delete()

                if reassigned:
                    # Park below every existing id so no orphan row can already
                    # hold a temporary id and trip the unique constraint.
                    park = min([0] + [ch.chapter_id for ch in existing_list]) - 1
                    for index, (chapter, _) in enumerate(reassigned, start=1):
                        chapter.chapter_id = park - index + 1
                    Chapter.objects.bulk_update(
                        [chapter for chapter, _ in reassigned], ['chapter_id']
                    )

                # Bulk create new chapters
                if new_chapters:
                    Chapter.objects.bulk_create(new_chapters)

                # Bulk update existing chapters
                if chapters_to_update:
                    for chapter, final_id in reassigned:
                        chapter.chapter_id = final_id
                    fields_to_update = ['chapter_id', 'url', 'title', 'volume', 'volume_title', 'images', 'has_content']
                    Chapter.objects.bulk_update(chapters_to_update, fields_to_update)
            
            # Update last_chapter_update timestamp
            novel_from_source.last_chapter_update = timezone.now()
            novel_from_source.save(update_fields=['last_chapter_update'])
        
        # Generate overview image
        novel_from_source.generate_overview_image()
        # Generate miniature cover image
        novel_from_source.generate_cover_min()
        
        return novel_from_source

    def generate_overview_image(self):
        """
        Generate an overview image for this novel source
        """
        try:
            # Use dynamic import to avoid circular dependency
            from ..services import cover_service
            return cover_service.generate_overview(self)
        except Exception as e:
            print(f"Error generating overview image for {self.title}: {e}")
            return False
    
    def generate_cover_min(self, width=200, height=300, quality=80):
        """
        Generate a miniature WebP version of the cover image
        """
        try:
            # Use dynamic import to avoid circular dependency
            from ..services import cover_service
            return cover_service.generate_cover_min(self, width, height, quality)
        except Exception as e:
            print(f"Error generating miniature cover for {self.title}: {e}")
            return False

    def delete(self, *args, **kwargs):
        """
        Override the delete method to also remove the source folder
        """
        # Check if we have a source path and it exists
        print(f"Deleting source folder: {self.source_path}")
        if self.source_path:
            full_source_path = self.absolute_source_path
            if full_source_path and os.path.exists(full_source_path) and os.path.isdir(full_source_path):
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
        is_new = self._state.adding
        old_vote_type = None

        if not is_new:
            try:
                old_vote_type = SourceVote.objects.get(pk=self.pk).vote_type
            except SourceVote.DoesNotExist:
                is_new = True

        super().save(*args, **kwargs)

        # Update counts atomically so concurrent votes don't lose increments.
        source_pk = self.source_id

        if is_new:
            if self.vote_type == 'up':
                NovelFromSource.objects.filter(pk=source_pk).update(
                    upvotes=models.F('upvotes') + 1
                )
            else:
                NovelFromSource.objects.filter(pk=source_pk).update(
                    downvotes=models.F('downvotes') + 1
                )
        elif old_vote_type and old_vote_type != self.vote_type:
            if self.vote_type == 'up':
                NovelFromSource.objects.filter(pk=source_pk).update(
                    upvotes=models.F('upvotes') + 1,
                    downvotes=models.F('downvotes') - 1,
                )
            else:
                NovelFromSource.objects.filter(pk=source_pk).update(
                    downvotes=models.F('downvotes') + 1,
                    upvotes=models.F('upvotes') - 1,
                )
