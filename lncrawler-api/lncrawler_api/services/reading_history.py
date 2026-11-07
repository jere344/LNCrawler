"""Reading history: where each user is in each novel, shared by the reader and the audiobook progress."""
from django.db import transaction

from ..models.users_models import ReadingHistory


def set_reading_position(user, novel, source, chapter, position, forward_only=False):
    """Point the user's reading history of ``novel`` at ``chapter``, ``position`` (0 to 1) into it.

    With ``forward_only``, a row already further on stays as it is: a chapter before its current one, or the
    same chapter at or past ``position``. The row is locked for the check, so concurrent saves cannot both
    pass it. Returns the row.
    """
    position = min(max(position, 0), 1)
    with transaction.atomic():
        reading_history, created = ReadingHistory.objects.get_or_create(
            user=user,
            novel=novel,
            defaults={'source': source, 'current_chapter': chapter, 'position': position},
        )
        if created:
            return reading_history
        reading_history = (
            ReadingHistory.objects.select_for_update(of=("self",))
            .select_related("current_chapter")
            .get(pk=reading_history.pk)
        )
        current = reading_history.current_chapter
        if forward_only and current is not None and (
            chapter.chapter_id < current.chapter_id
            or (chapter.chapter_id == current.chapter_id and position <= reading_history.position)
        ):
            return reading_history
        reading_history.source = source
        reading_history.current_chapter = chapter
        reading_history.position = position
        reading_history.save()
    return reading_history
