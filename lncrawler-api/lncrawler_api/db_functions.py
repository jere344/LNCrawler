from django.db.models import Func, TextField
from django.db.models.functions import Upper


class ImmutableUnaccent(Func):
    """Postgres immutable_unaccent() (created in migration 0099), usable in indexes."""
    function = "immutable_unaccent"
    output_field = TextField()


def search_norm(expression):
    """Accent- and case-folded form of a text column, used for the search_title / search_name
    generated columns and their trigram indexes (novel_search_title_trgm_idx, nfs_search_title_trgm_idx,
    alttitle_search_name_trgm_idx). Changing the unaccent rules requires recomputing those stored columns.
    """
    return ImmutableUnaccent(Upper(expression))
