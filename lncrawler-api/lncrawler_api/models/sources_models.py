from django.db import models, transaction
from django.db.models import Case, Exists, OuterRef, Value, When
import logging
import os
import re
import json
import shutil
from django.conf import settings
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db.models.functions import Upper
from django.utils import timezone
from django.utils.text import slugify as django_slugify

from .novels_models import Novel, NovelAlias, Author, Editor, Translator, Tag, AlternativeTitle

logger = logging.getLogger('lncrawler_api')
from .chapter_models import Volume, Chapter
from .external_source_models import ExternalSource
from .source_helpers import resolve_output_path, truncate
from .source_links import (
    AuthorImportError,
    TAG_IMPORT_ATTEMPTS,
    TagImportError,
    TagImportRetry,
    _set_source_authors,
)
from ..db_locks import lock_pks
from ..utils import chapter_utils, lncrawler_paths
from ..utils.slug import slugify
from ..utils.title_signals import edition_label_from_title, same_work

CHAPTER_BULK_CHUNK = 500


class SourceFolderConflict(Exception):
    """A source folder belongs to another source, so its import is refused."""


def _set_source_tags(novel_from_source, names):
    """Replace ``novel_from_source``'s tags with the tags named ``names``.

    Each attempt is its own transaction when called without an outer atomic, or a
    savepoint when called inside one: resolve the names, lock the sorted union of
    their tags in one statement, then link. If a tag was merged away in the
    meantime it is missing from the lock result; that attempt rolls back
    (releasing its locks) and the names are resolved again. Locks are never taken
    in two rounds, so two imports cannot wait on each other.

    Raises ``TagImportError`` when every attempt failed; the caller decides
    whether the rest of the import continues.
    """
    names = [name for name in names if name]
    for _ in range(TAG_IMPORT_ATTEMPTS):
        try:
            with transaction.atomic():
                tags = {}
                for name in names:
                    tag = Tag.resolve(name)
                    tags[tag.pk] = tag
                pks = sorted(tags)
                if lock_pks(Tag, pks) != set(pks):
                    raise TagImportRetry()
                novel_from_source.tags.set([tags[pk] for pk in pks])
                is_adult = novel_from_source.adult_from_source or any(tags[pk].is_adult for pk in pks)
                if is_adult != novel_from_source.is_adult:
                    novel_from_source.is_adult = is_adult
                    NovelFromSource.objects.filter(pk=novel_from_source.pk).update(is_adult=is_adult)
                return
        except TagImportRetry:
            continue
    raise TagImportError(
        f"tags kept changing during import after {TAG_IMPORT_ATTEMPTS} attempts"
    )


def refresh_adult(queryset=None):
    """Recompute the effective ``is_adult`` of sources (all of them by default).

    A source is adult when its own flag (``adult_from_source``: meta.json or an
    admin) is set, or when it carries an R18 tag. Both directions are applied,
    so unflagging a tag clears the sources it alone made adult. A novel is adult
    when any of its sources is. Returns ``(flagged, cleared)``.
    """
    queryset = NovelFromSource.objects.all() if queryset is None else queryset
    r18_tag = NovelFromSource.tags.through.objects.filter(
        novelfromsource_id=OuterRef("pk"), tag__is_adult=True
    )
    computed = queryset.annotate(
        computed_adult=Case(
            When(adult_from_source=True, then=Value(True)),
            When(Exists(r18_tag), then=Value(True)),
            default=Value(False),
            output_field=models.BooleanField(),
        )
    )
    flagged = NovelFromSource.objects.filter(
        pk__in=computed.filter(computed_adult=True, is_adult=False).values("pk")
    ).update(is_adult=True)
    cleared = NovelFromSource.objects.filter(
        pk__in=computed.filter(computed_adult=False, is_adult=True).values("pk")
    ).update(is_adult=False)
    return flagged, cleared


def refresh_adult_for_tags(tag_pks):
    """``refresh_adult`` for the sources carrying any of ``tag_pks``, after
    those tags were flagged or unflagged R18 (or merged)."""
    if not tag_pks:
        return 0, 0
    return refresh_adult(NovelFromSource.objects.filter(tags__pk__in=tag_pks))


def bulk_update_chunked(objects, fields, chunk_size=CHAPTER_BULK_CHUNK):
    # Django's bulk_update builds one statement with a CASE/WHEN per row per
    # field; a large chapter list becomes a single multi-MB query that can OOM
    # the postgres backend. Chunk it. bulk_update has no batch_size argument.
    for start in range(0, len(objects), chunk_size):
        Chapter.objects.bulk_update(objects[start:start + chunk_size], fields)


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
    # Free-form edition label supplied by the crawler (e.g. "Web Novel",
    # "Official translation"). Blank when unknown; see title_signals.effective_edition.
    edition = models.CharField(max_length=100, blank=True, default="")
    source_url = models.CharField(max_length=500)
    external_source = models.ForeignKey(ExternalSource, on_delete=models.CASCADE, related_name='novels')
    source_slug = models.SlugField(max_length=100, blank=True)
    cover_url = models.CharField(max_length=500, null=True, blank=True)
    
    # Path information relative to settings.LNCRAWL_OUTPUT_PATH
    source_path = models.CharField(max_length=500, null=True, blank=True, db_index=True)
    cover_path = models.CharField(max_length=500, null=True, blank=True)
    cover_min_path = models.CharField(max_length=500, null=True, blank=True)
    overview_picture_path = models.CharField(max_length=500, null=True, blank=True) 

    # 64-bit dHash (16 hex chars) of the cover image, used to group the same
    # cover across sources/languages. Computed from cover.min.webp only for real
    # (non-placeholder) covers; NULL when there is no cover.
    cover_phash = models.CharField(max_length=16, null=True, blank=True, db_index=True)
    
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
    # Effective adult flag, the one every query filters on. Derived: the
    # source's own flag OR any R18 tag (see refresh_adult). Never edit it directly.
    is_adult = models.BooleanField(default=False)
    # The source's own adult flag: the crawler's meta.json value, or an admin's.
    adult_from_source = models.BooleanField(default=False)
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
        constraints = [
            # Views look sources up by (novel, source_slug); two rows sharing a
            # slug would make that lookup raise MultipleObjectsReturned.
            models.UniqueConstraint(
                fields=['novel', 'source_slug'],
                condition=~models.Q(source_slug=''),
                name='unique_source_slug_per_novel',
            ),
        ]
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
    def vote_score(self):
        return self.upvotes - self.downvotes
    
    @classmethod
    def unique_source_slug(cls, novel, base, exclude_pk=None):
        """Return a slug that no other source of ``novel`` already uses.

        The first claimant keeps ``base``; later ones get ``-2``, ``-3`` ...
        appended, with ``base`` shortened so the result stays within the 100
        character column. ``exclude_pk`` is the row being named, so it does not
        collide with its own current slug. A blank slug is never suffixed: the
        unique constraint does not apply to blanks.
        """
        base = (base or "")[:100]
        if not base:
            return base
        taken = set(
            cls.objects.filter(novel=novel)
            .exclude(pk=exclude_pk)
            .values_list("source_slug", flat=True)
        )
        if base not in taken:
            return base
        n = 2
        while True:
            suffix = f"-{n}"
            candidate = base[: 100 - len(suffix)] + suffix
            if candidate not in taken:
                return candidate
            n += 1

    @classmethod
    def _taken_folder_names(cls, novel, exclude_pk=None):
        """Folder basenames already used by the sources of ``novel``."""
        rows = cls.objects.filter(novel=novel).exclude(source_path__isnull=True).exclude(source_path='')
        if exclude_pk is not None:
            rows = rows.exclude(pk=exclude_pk)
        return {os.path.basename(path) for path in rows.values_list('source_path', flat=True)}

    @classmethod
    def _folder_owner(cls, source_rel, exclude_pk=None):
        """The row (other than ``exclude_pk``) whose folder is ``source_rel``, if any."""
        rows = cls.objects.filter(source_path=source_rel)
        if exclude_pk is not None:
            rows = rows.exclude(pk=exclude_pk)
        return rows.order_by('pk').first()

    @classmethod
    def _consolidate_source_directory(cls, source_dir, output_path, novel, existing_source, title='', edition=''):
        """
        Return the canonical ``(source_dir, source_path, meta_json_path,
        cover_path)`` for a source, relocating its files when needed.

        Destination preference:
          1. where the existing ``NovelFromSource`` row already lives, so
             updates stay anchored to the canonical folder,
          2. the canonical novel folder plus the folder's own name (``site``,
             ``site [ln]``, ``site [2]``), used for a brand-new source.

        Whenever the preferred folder is owned by another row of the novel, a
        free ``<site> [..]`` folder is chosen beside it instead, so two works of
        one site never share files. A folder owned by another row is never
        moved: that raises ``SourceFolderConflict``.
        """
        own_pk = existing_source.pk if existing_source is not None else None
        source_rel = os.path.relpath(source_dir, settings.LNCRAWL_OUTPUT_PATH)
        owner = cls._folder_owner(source_rel, exclude_pk=own_pk)
        if owner is not None:
            # Moving it would carry another source's files away and leave that
            # row pointing at nothing. Fail the import of this folder instead.
            logger.error(
                "Refusing to import '%s': it belongs to source %s ('%s')",
                source_rel, owner.pk, owner.title,
            )
            raise SourceFolderConflict(
                f"'{source_rel}' belongs to another source ('{owner.title}'); "
                "the import was cancelled."
            )

        target_abs = None
        if existing_source is not None and existing_source.source_path:
            target_abs = os.path.join(output_path, existing_source.source_path)
            parent_abs = os.path.dirname(target_abs)
        else:
            # ``slug`` is the folder identity ``from_meta_json`` derives, so use
            # it when ``novel_path`` was never recorded.
            canonical_dir = novel.novel_path or novel.slug
            if canonical_dir:
                parent_abs = os.path.join(output_path, canonical_dir)
                # Keep the folder's own name (``site [ln]``, ``site [2]``) unless
                # another row of this novel already uses it.
                target_abs = os.path.join(parent_abs, os.path.basename(source_dir))

        if target_abs is not None:
            taken = cls._taken_folder_names(novel, exclude_pk=own_pk)
            target_rel = os.path.relpath(target_abs, settings.LNCRAWL_OUTPUT_PATH)
            target_owned = cls._folder_owner(target_rel, exclude_pk=own_pk) is not None
            name_taken = existing_source is None and os.path.basename(target_abs) in taken
            if target_owned or name_taken:
                # Never merge into another row's folder: pick a free one beside it.
                folder = lncrawler_paths.free_source_folder(
                    parent_abs,
                    lncrawler_paths.site_name_from_folder(os.path.basename(source_dir)),
                    edition or edition_label_from_title(title),
                    taken,
                )
                target_abs = os.path.join(parent_abs, folder)

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
    def from_meta_json(cls, meta_json_path, added_by=None):
        """
        Create a NovelFromSource instance from a meta.json file

        ``added_by`` is recorded on a newly created Novel only; an update of an
        existing novel never rewrites its original contributor.
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
        # Free-form edition from the crawler; the title marker is the fallback.
        crawled_edition = (novel_data.get('edition') or '').strip()[:100]
        edition = crawled_edition or edition_label_from_title(title)
        
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

        # The folder is the real identity: resolve by path first so a change in
        # the slug algorithm cannot spawn a duplicate for an existing folder
        # whose stored slug was derived the old way.
        # ponytail: novel_path has no unique constraint; order_by('pk') keeps a
        # shared path deterministic. Add a partial unique index if dupes appear.
        novel = Novel.objects.filter(novel_path=novel_path).order_by('pk').first()
        if novel is None:
            # Rows imported before novel_path was recorded, or before the switch
            # to python-slugify, still carry a slug derived by Django's slugify
            # (which differs on apostrophes and non-ASCII). Match that too so a
            # re-crawl reattaches instead of creating a duplicate.
            legacy_slug = django_slugify(os.path.basename(novel_path))
            if legacy_slug != novel_slug:
                novel = Novel.objects.filter(slug=legacy_slug).first()
        if novel is None:
            alias = NovelAlias.objects.filter(slug=novel_slug).select_related('novel').first()
            if alias is not None:
                novel = alias.novel
            else:
                novel, created = Novel.objects.get_or_create(
                    slug=novel_slug,
                    defaults={
                        'title': title,
                        'novel_path': novel_path,
                        'added_by': added_by,
                    }
                )
        
        # Create or get the external source. A " [..]" suffix on the folder
        # marks a second source of the same site in this novel (e.g. "foo [ln]"),
        # so the site is the folder name without it.
        source_name = lncrawler_paths.site_name_from_folder(os.path.basename(source_dir))
        external_source, created = ExternalSource.objects.get_or_create(
            source_name=source_name
        )
        
        # Create or update the NovelFromSource.
        # Identity: the exact URL first. Failing that, the same site with the
        # same work: one site can list a web novel and a light novel under one
        # novel, so the title decides between rows of that site. A mirror
        # domain under a changed URL still updates its row.
        source_url = truncate(novel_data.get('url', ''))

        novel_from_source = cls.objects.filter(novel=novel, source_url=source_url).order_by('pk').first()
        if novel_from_source is None:
            for candidate in cls.objects.filter(novel=novel, external_source=external_source).order_by('pk'):
                # A meta.json without an edition says nothing against the
                # label the row already carries.
                # The title's own edition comes before the stored one: an LN
                # title must not adopt the WN row's label.
                incoming = crawled_edition or edition or candidate.edition
                if same_work(candidate.title, candidate.edition, title, incoming):
                    novel_from_source = candidate
                    break
        if not crawled_edition and novel_from_source is not None and novel_from_source.edition:
            # ...and must not wipe it either.
            edition = novel_from_source.edition
        existing_source = novel_from_source

        # Store files under the canonical novel folder (and keep an update in
        # the folder it already lives in). This runs before any row is deleted:
        # a folder that belongs to another source refuses the import outright.
        source_dir, source_path, meta_json_path, cover_path = cls._consolidate_source_directory(
            source_dir=source_dir,
            output_path=output_path,
            novel=novel,
            existing_source=existing_source,
            title=title,
            edition=edition,
        )

        if novel_from_source is None:
            novel_from_source = cls(novel=novel)
        else:
            # Drop a legacy duplicate alias row that would violate (novel, source_url).
            cls.objects.filter(novel=novel, source_url=source_url).exclude(pk=novel_from_source.pk).delete()
        # Slug from the final folder name, so a second source of a site gets
        # its own ("foo-ln") rather than sharing the plain site slug.
        source_slug = slugify(os.path.basename(source_dir))

        novel_from_source.novel = novel
        novel_from_source.source_url = source_url
        novel_from_source.external_source = external_source
        novel_from_source.title = truncate(title)
        novel_from_source.edition = edition
        novel_from_source.source_slug = cls.unique_source_slug(
            novel, truncate(source_slug, 100), exclude_pk=novel_from_source.pk
        )
        novel_from_source.source_path = truncate(source_path)
        # Only keep the path if the file actually exists: the crawler no longer
        # writes a placeholder cover, so a missing cover.jpg must stay NULL.
        novel_from_source.cover_path = None
        if cover_path and os.path.isfile(os.path.join(settings.LNCRAWL_OUTPUT_PATH, cover_path)):
            novel_from_source.cover_path = truncate(cover_path)
        novel_from_source.cover_url = truncate(novel_data.get('cover_url', ''))
        novel_from_source.language = novel_data.get('language', 'en')
        novel_from_source.status = novel_data.get('status', 'Unknown')
        novel_from_source.synopsis = novel_data.get('synopsis', '')
        novel_from_source.adult_from_source = bool(novel_data.get('is_adult', False))
        # Effective flag; _set_source_tags recomputes it once the new tags are linked.
        novel_from_source.is_adult = novel_from_source.adult_from_source or (
            novel_from_source.pk is not None
            and novel_from_source.tags.filter(is_adult=True).exists()
        )
        novel_from_source.original_publisher = truncate(novel_data.get('original_publisher', ''))
        novel_from_source.english_publisher = truncate(novel_data.get('english_publisher', ''))
        novel_from_source.novelupdates_url = truncate(novel_data.get('novelupdates_url', ''))
        novel_from_source.meta_file_path = meta_json_path
        novel_from_source.last_chapter_update = timezone.now()
        novel_from_source.save()
        
        # Handle authors (list of strings)
        try:
            _set_source_authors(novel_from_source, novel_data.get('authors', []))
        except AuthorImportError:
            # Authors are metadata: never let them block the chapters and titles.
            logger.warning(
                "Skipped authors for source %s: they kept changing during import",
                novel_from_source.pk,
            )
        
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
        try:
            _set_source_tags(novel_from_source, tags_list)
        except TagImportError:
            # Tags are metadata: never let them block the chapters and titles.
            logger.warning(
                "Skipped tags for source %s: they kept changing during import",
                novel_from_source.pk,
            )
        
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
            # Rows no incoming chapter claims (e.g. removed from the tail of the
            # source). Pruning (orphans and volumes) is skipped when a sizeable
            # novel shrank by more than half: that looks like a partial scrape,
            # not a real removal. Stale-collision deletion above is unaffected.
            incoming_count = len(assigned_ids)
            prune_allowed = not (
                len(existing_list) >= 20 and incoming_count < len(existing_list) / 2
            )
            if not prune_allowed:
                logger.warning(
                    "Skipped pruning for source %s: %d incoming chapters vs %d existing",
                    novel_from_source.pk, incoming_count, len(existing_list),
                )
            orphans = []
            if target_ids and prune_allowed:
                stale_pks = {ch.pk for ch in stale}
                orphans = [
                    ch for ch in existing_list
                    if ch.pk not in used_pks and ch.pk not in stale_pks
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

                if orphans:
                    # Comment.chapter is CASCADE and ReadingHistory.last_read_chapter
                    # is SET_NULL, so an orphan with user data is kept rather than
                    # silently losing comments or reading progress. One query per
                    # relation covers all orphans at once.
                    orphan_pks = [ch.pk for ch in orphans]
                    with_user_data = set()
                    for rel in Chapter._meta.related_objects:
                        field = rel.field.name
                        with_user_data.update(
                            rel.related_model._default_manager
                            .filter(**{f"{field}__in": orphan_pks})
                            .values_list(field, flat=True)
                        )
                    removable = [pk for pk in orphan_pks if pk not in with_user_data]
                    kept = len(orphan_pks) - len(removable)
                    if kept:
                        logger.debug("Kept %d orphan chapters with user data", kept)
                    if removable:
                        Chapter.objects.filter(pk__in=removable).delete()

                # Drop volumes the source no longer lists. Skipped together with
                # the chapter prune, and when the list is empty.
                volume_ids = [v.get('id') for v in (novel_data.get('volumes') or [])]
                if prune_allowed and volume_ids:
                    Volume.objects.filter(novel_from_source=novel_from_source).exclude(
                        volume_id__in=volume_ids
                    ).delete()

                if reassigned:
                    # Park below every existing id so no orphan row can already
                    # hold a temporary id and trip the unique constraint.
                    park = min([0] + [ch.chapter_id for ch in existing_list]) - 1
                    for index, (chapter, _) in enumerate(reassigned, start=1):
                        chapter.chapter_id = park - index + 1
                    bulk_update_chunked(
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
                    bulk_update_chunked(chapters_to_update, fields_to_update)
            
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
            from ..services.covers.overview import generate_overview
            return generate_overview(self)
        except Exception as e:
            print(f"Error generating overview image for {self.title}: {e}")
            return False
    
    def generate_cover_min(self, width=200, height=300, quality=80):
        """
        Generate a miniature WebP version of the cover image
        """
        try:
            # Use dynamic import to avoid circular dependency
            from ..services.covers.resize import generate_cover_min
            return generate_cover_min(self, width, height, quality)
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
