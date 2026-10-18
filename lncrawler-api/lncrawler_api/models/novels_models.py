from django.db import IntegrityError, models
import uuid
from django.conf import settings
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.db.models import F
from django.db.models.functions import Upper

from ..utils.tag_utils import normalize_tag


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
    comment_count = models.PositiveIntegerField(default=0)
    is_dmca = models.BooleanField(default=False, db_index=True)

    # Periodic projections of the sources' views and the ratings, used only for
    # search ordering; refreshed by the refresh_novel_rankings scheduler task
    # (cards still show live values). The rank_ prefix avoids clashing with the
    # total_views/week_views/avg_rating annotations used across the code.
    rank_total_views = models.BigIntegerField(default=0)
    rank_week_views = models.BigIntegerField(default=0)
    rank_avg_rating = models.FloatField(default=0.0)

    # The user whose download job first imported this novel (null for
    # anonymous submissions and for novels imported before this was tracked).
    # Set once on creation and never rewritten by later updates.
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='added_novels',
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['title'], name='novel_title_idx'),
            models.Index(fields=['-created_at'], name='novel_created_at_idx'),
            models.Index(fields=['added_by', '-created_at'], name='novel_added_by_idx'),
            GinIndex(OpClass(Upper('title'), name='gin_trgm_ops'), name='novel_title_trgm_idx'),
            models.Index(fields=['-rank_total_views', 'title'], name='novel_rank_views_idx'),
            models.Index(fields=['-rank_week_views', 'title'], name='novel_rank_week_idx'),
            models.Index(fields=['-rank_avg_rating', 'title'], name='novel_rank_rating_idx'),
        ]
    
    def __str__(self):
        return self.title
    
    @property
    def sources_count(self):
        return self.sources.count()
        
    def increment_comment_count(self):
        """
        Increment the comment count for the novel
        """
        Novel.objects.filter(pk=self.pk).update(
            comment_count=F('comment_count') + 1
        )
        # Refresh from database to get the latest values
        self.refresh_from_db()


class NovelAlias(models.Model):
    """
    Redirect from an obsolete novel slug to the canonical novel it was merged
    into.

    ``NovelFromSource.from_meta_json`` identifies a novel by the slugified name
    of its output folder. When two folders hold the same story and are merged,
    a future crawl of the old folder name would otherwise recreate a fresh
    ``Novel`` and undo the merge. Recording the old slug here makes that future
    crawl attach to the surviving novel instead.
    """
    slug = models.SlugField(max_length=255, unique=True)
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='aliases')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Novel alias'
        verbose_name_plural = 'Novel aliases'
        ordering = ['slug']

    def __str__(self):
        return f"{self.slug} -> {self.novel.slug}"


class Person(models.Model):
    """Base model for people involved with novels (authors, editors, translators)"""
    name = models.CharField(max_length=255)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class Author(Person):
    """Author of a novel"""
    class Meta:
        indexes = [
            GinIndex(OpClass(Upper('name'), name='gin_trgm_ops'), name='author_name_trgm_idx'),
        ]


class Editor(Person):
    """Editor of a novel"""
    pass


class Translator(Person):
    """Translator of a novel"""
    pass


class Tag(models.Model):
    """Tags for novels"""
    name = models.CharField(max_length=100, unique=True)
    # Comparison key (case/accent/plural/punctuation-insensitive), always derived
    # from ``name`` in save(). Unique, so two tags can never differ only trivially.
    normalized = models.CharField(max_length=100, unique=True, editable=False)
    # Float32 bytes of the name's embedding, and the model that produced them.
    embedding = models.BinaryField(null=True, editable=False)
    embedding_model = models.CharField(max_length=100, blank=True, default="", editable=False)
    # R18 tag: any source carrying it is treated as adult (see mark_sources_adult).
    is_adult = models.BooleanField(default=False, db_index=True)

    class Meta:
        indexes = [
            GinIndex(OpClass(Upper('name'), name='gin_trgm_ops'), name='tag_name_trgm_idx'),
            GinIndex(OpClass('normalized', name='gin_trgm_ops'), name='tag_normalized_trgm_idx'),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.normalized = normalize_tag(self.name)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "name" in update_fields:
            kwargs["update_fields"] = {*update_fields, "normalized"}
        super().save(*args, **kwargs)

    @classmethod
    def find(cls, name):
        """Return the existing tag for ``name`` (or a merged-away alias of it), else None.

        Never creates a tag, so read paths such as filters can use it safely.
        """
        key = normalize_tag(name)
        tag = cls.objects.filter(normalized=key).first()
        if tag is not None:
            return tag
        alias = TagAlias.objects.filter(normalized=key).select_related('tag').first()
        return alias.tag if alias is not None else None

    @classmethod
    def resolve(cls, name):
        """Return the tag for ``name``, following a merged-away alias first.

        Keeps re-imports from recreating a tag that was merged into another, and
        folds case/accent/plural variants onto the existing tag.
        """
        name = name.strip()[: cls._meta.get_field('name').max_length]
        tag = cls.find(name)
        if tag is not None:
            return tag
        key = normalize_tag(name)
        try:
            tag, _ = cls.objects.get_or_create(normalized=key, defaults={'name': name})
        except IntegrityError:
            # Lost a race with a concurrent import of the same tag (or alias).
            tag = cls.find(name)
            if tag is None:
                raise
        return tag


class TagAlias(models.Model):
    """A merged-away tag name pointing at its canonical Tag."""
    name = models.CharField(max_length=100, unique=True)
    normalized = models.CharField(max_length=100, db_index=True, editable=False)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name='aliases')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'tag alias'
        verbose_name_plural = 'tag aliases'
        ordering = ['name']
        indexes = [
            GinIndex(OpClass(Upper('name'), name='gin_trgm_ops'), name='tagalias_name_trgm_idx'),
        ]

    def __str__(self):
        return f"{self.name} -> {self.tag.name}"

    def save(self, *args, **kwargs):
        self.normalized = normalize_tag(self.name)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "name" in update_fields:
            kwargs["update_fields"] = {*update_fields, "normalized"}
        super().save(*args, **kwargs)


class AlternativeTitle(models.Model):
    """Alternative / native title a novel is known by on a given source."""
    name = models.CharField(max_length=500, unique=True)

    class Meta:
        ordering = ['name']
        indexes = [
            GinIndex(OpClass(Upper('name'), name='gin_trgm_ops'), name='alttitle_name_trgm_idx'),
        ]

    def __str__(self):
        return self.name


class NovelRating(models.Model):
    """
    Tracks user ratings for novels (1-5 stars)
    """
    RATING_CHOICES = [
        (1, '1 Star'),
        (2, '2 Stars'),
        (3, '3 Stars'),
        (4, '4 Stars'),
        (5, '5 Stars'),
    ]
    
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='ratings')
    # Logged-in users are keyed by user; anonymous visitors fall back to IP.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True, related_name='novel_ratings',
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    rating = models.IntegerField(choices=RATING_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['novel', 'user'],
                condition=models.Q(user__isnull=False),
                name='unique_rating_per_user',
            ),
            models.UniqueConstraint(
                fields=['novel', 'ip_address'],
                condition=models.Q(user__isnull=True),
                name='unique_rating_per_anon_ip',
            ),
        ]
        
    def __str__(self):
        who = self.user.username if self.user_id else self.ip_address
        return f"Rating {self.rating} for {self.novel.title} by {who}"


class WeeklySourceView(models.Model):
    """
    Views for one source (NovelFromSource) as time buckets. Recent views are
    stored one row per day (granularity='day', day = the calendar day); buckets
    older than the consolidation window are rolled up by
    ``consolidate_source_views`` into one row per ISO week (granularity='week',
    day = that week's Monday).

    Views are tracked per source because a novel can be available in several
    languages and popularity must be attributable to a language. The all-time
    total is a rebuildable projection kept on NovelFromSource.total_views, so
    this table stays the single event record.

    The trailing WINDOW_DAYS days of daily buckets are summed to produce the
    rolling "weekly views" shown in the UI, so the number slides day by day
    instead of resetting at the start of each calendar week.
    """
    WINDOW_DAYS = 7
    CONSOLIDATION_DAYS = 30  # Keep daily buckets this long before rolling up

    DAY = 'day'
    WEEK = 'week'
    GRANULARITY_CHOICES = [(DAY, 'day'), (WEEK, 'week')]

    source = models.ForeignKey(
        'NovelFromSource', on_delete=models.CASCADE, related_name='weekly_views'
    )
    day = models.DateField()  # Day for daily rows, Monday for weekly rows
    granularity = models.CharField(max_length=4, choices=GRANULARITY_CHOICES, default=DAY)
    views = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('source', 'granularity', 'day')
        indexes = [
            models.Index(fields=['granularity', 'day']),
            models.Index(fields=['source', 'granularity', 'day']),
        ]

    def __str__(self):
        period = self.day if self.granularity == self.DAY else f"week of {self.day}"
        return f"{self.source.title}: {self.views} views ({period})"

    @classmethod
    def window_start(cls):
        """First day included in the trailing window (today inclusive)."""
        from datetime import date, timedelta
        return date.today() - timedelta(days=cls.WINDOW_DAYS - 1)

    @classmethod
    def increment_for_source(cls, source):
        """
        Increment today's view count for a source and its all-time projection.

        Today's bucket is bumped with a single upsert (no read-back), so the
        transaction stays two statements long.
        """
        from datetime import date
        from django.db import connection, transaction

        from .sources_models import NovelFromSource

        table = cls._meta.db_table
        source_col = cls._meta.get_field('source').column
        granularity_col = cls._meta.get_field('granularity').column
        day_col = cls._meta.get_field('day').column
        views_col = cls._meta.get_field('views').column

        today = date.today()
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {table} ({source_col}, {granularity_col}, {day_col}, {views_col}) "
                f"VALUES (%s, %s, %s, 1) "
                f"ON CONFLICT ({source_col}, {granularity_col}, {day_col}) "
                f"DO UPDATE SET {views_col} = {table}.{views_col} + 1",
                [source.pk, cls.DAY, today],
            )
            NovelFromSource.objects.filter(pk=source.pk).update(
                total_views=F('total_views') + 1
            )


class NovelSimilarity(models.Model):
    """
    Stores similarity scores between novels
    """
    from_novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='similar_to')
    to_novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='similar_from')
    similarity = models.FloatField(default=0.0, help_text="Similarity score between 0 and 1")
    
    class Meta:
        unique_together = ('from_novel', 'to_novel')
        verbose_name_plural = "Novel Similarities"
    
    def __str__(self):
        return f"{self.from_novel.title} → {self.to_novel.title}: {self.similarity}"