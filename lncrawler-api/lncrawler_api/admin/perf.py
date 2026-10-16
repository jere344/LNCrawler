from django.core.paginator import Paginator
from django.db.models import QuerySet
from django.utils.functional import cached_property


class CappedCountPaginator(Paginator):
    """Paginator that bounds the COUNT(*) so huge tables stay responsive.

    Exact count while the queryset has fewer than ``count_cap`` rows, clamped
    to ``count_cap`` above that. Ordering is stripped from the counting
    subquery so a default ``ORDER BY`` can't force a full sort.

    ponytail: rows past ``count_cap`` are unreachable via pagination (the page
    count clamps at cap/per_page). Sized so the last reachable page is far
    beyond practical manual browsing; raise it or move to keyset pagination if
    deep navigation is ever needed.
    """

    count_cap = 10_000

    @cached_property
    def count(self):
        qs = self.object_list
        if isinstance(qs, QuerySet):
            return qs.order_by()[: self.count_cap].count()
        return len(qs)

