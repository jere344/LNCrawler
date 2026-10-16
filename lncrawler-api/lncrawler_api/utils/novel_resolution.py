from django.http import Http404


def resolve_novel_slug(novel_slug):
    """
    Return the ``Novel`` for a slug, following a merge alias when the slug was
    superseded by a merge.

    Novel detail, source, chapter and comment endpoints all start from the
    novel slug in the URL. Resolving aliases here keeps old bookmarks working
    after two novels are merged. Raises ``Http404`` when neither a novel nor an
    alias matches, mirroring ``get_object_or_404``.
    """
    from ..models import Novel, NovelAlias

    novel = Novel.objects.filter(slug=novel_slug).first()
    if novel is not None:
        return novel

    alias = (
        NovelAlias.objects.filter(slug=novel_slug).select_related("novel").first()
    )
    if alias is not None:
        return alias.novel

    raise Http404(f"No novel found matching '{novel_slug}'.")
