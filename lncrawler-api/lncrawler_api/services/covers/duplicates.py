from django.db.models import Count

from ...models import NovelFromSource


def duplicate_cover_groups(min_novels=2):
    """Cover hashes shared by at least ``min_novels`` distinct novels, most common first."""
    return (
        NovelFromSource.objects.exclude(cover_phash__isnull=True)
        .exclude(cover_phash='')
        .values('cover_phash')
        .annotate(sources=Count('id'), novels=Count('novel', distinct=True))
        .filter(novels__gte=min_novels)
        .order_by('-novels', '-sources')
    )
