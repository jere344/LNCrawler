"""Reading history updates shared by the chapter read marks and the audiobook progress."""
from ..models.users_models import ReadingHistory


def advance_reading_history(user, novel, source, chapter):
    """Move the user's reading history of a novel forward to ``chapter``, never back.

    Returns ``(reading_history, created, moved)``. The caller runs this inside a transaction: the row is
    locked for the check, so concurrent marks cannot both pass it.
    """
    reading_history, created = ReadingHistory.objects.get_or_create(
        user=user,
        novel=novel,
        defaults={'source': source, 'last_read_chapter': chapter},
    )
    if created:
        return reading_history, True, True
    reading_history = (
        ReadingHistory.objects.select_for_update(of=("self",))
        .select_related("last_read_chapter")
        .get(pk=reading_history.pk)
    )
    current = (
        reading_history.last_read_chapter.chapter_id
        if reading_history.last_read_chapter
        else None
    )
    if current is not None and chapter.chapter_id <= current:
        return reading_history, False, False
    reading_history.source = source
    reading_history.last_read_chapter = chapter
    reading_history.save()
    return reading_history, False, True
