from django.contrib.auth import get_user_model
from django.test import TestCase

from lncrawler_api.admin.perf import CappedCountPaginator


class CappedCountPaginatorTests(TestCase):
    def _paginator(self, per_page=10, cap=None):
        qs = get_user_model().objects.order_by("pk")
        paginator = CappedCountPaginator(qs, per_page)
        if cap is not None:
            paginator.count_cap = cap
        return paginator

    def test_exact_count_below_cap(self):
        get_user_model().objects.bulk_create(
            [get_user_model()(username=f"u{i}", email=f"u{i}@example.com") for i in range(3)]
        )
        self.assertEqual(self._paginator(cap=100).count, 3)

    def test_count_clamped_at_cap(self):
        get_user_model().objects.bulk_create(
            [get_user_model()(username=f"u{i}", email=f"u{i}@example.com") for i in range(5)]
        )
        paginator = self._paginator(per_page=10, cap=2)
        self.assertEqual(paginator.count, 2)
        self.assertEqual(paginator.num_pages, 1)

    def test_count_exactly_at_cap(self):
        get_user_model().objects.bulk_create(
            [get_user_model()(username=f"u{i}", email=f"u{i}@example.com") for i in range(3)]
        )
        paginator = self._paginator(cap=3)
        self.assertEqual(paginator.count, 3)
        self.assertEqual(paginator.num_pages, 1)

    def test_accepts_non_queryset_object_list(self):
        paginator = CappedCountPaginator([1, 2, 3], 10)
        self.assertEqual(paginator.count, 3)

