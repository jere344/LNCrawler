from django.db import transaction

from ..db_locks import lock_pks
from .novels_models import Author


TAG_IMPORT_ATTEMPTS = 3


class TagImportRetry(Exception):
    """Internal per-attempt signal: a tag was merged away before it could be locked."""


class TagImportError(Exception):
    """Tags could not be linked after ``TAG_IMPORT_ATTEMPTS`` attempts."""


AUTHOR_IMPORT_ATTEMPTS = 3


class AuthorImportRetry(Exception):
    """Internal per-attempt signal: an author was merged away before it could be locked."""


class AuthorImportError(Exception):
    """Authors could not be linked after ``AUTHOR_IMPORT_ATTEMPTS`` attempts."""


def _set_source_authors(novel_from_source, names):
    """Replace ``novel_from_source``'s authors with the authors named ``names``.

    Same scheme as ``_set_source_tags``: each attempt resolves the names (following
    merged-away aliases), locks the sorted union of their authors in one statement,
    then links. ``merge_authors`` locks the same rows in the same order, so an
    author merged away in the meantime is missing from the lock result; that
    attempt rolls back and the names are resolved again. Blocked names are skipped
    (``Author.resolve`` returns None), and an author blocked during the import drops
    out of the lock result, so that attempt is retried too.

    Raises ``AuthorImportError`` when every attempt failed.
    """
    names = [name for name in names if name]
    for _ in range(AUTHOR_IMPORT_ATTEMPTS):
        try:
            with transaction.atomic():
                authors = {}
                for name in names:
                    author = Author.resolve(name)
                    if author is not None:
                        authors[author.pk] = author
                pks = sorted(authors)
                if lock_pks(Author, pks) != set(pks):
                    raise AuthorImportRetry()
                novel_from_source.authors.set([authors[pk] for pk in pks])
                return
        except AuthorImportRetry:
            continue
    raise AuthorImportError(
        f"authors kept changing during import after {AUTHOR_IMPORT_ATTEMPTS} attempts"
    )
