"""Regression tests for cover handling (overview fallback + dHash consistency)."""

import os

from PIL import Image

from ..models import ExternalSource, Novel
from ..services.cover_service import OverviewGenerator, dhash_file, generate_cover_min
from .helpers import MergeTestCase


class CoverServiceTests(MergeTestCase):
    def _make_covered_source(self):
        novel = Novel.objects.create(title="Covered", slug="covered", novel_path="covered")
        external = ExternalSource.objects.create(source_name="cover-site")
        source = self.make_source(novel, external, "Covered", "http://x/1", "covered", "site")
        cover_rel = os.path.join(source.source_path, "cover.jpg")
        Image.new("RGB", (400, 600), (10, 60, 120)).save(
            os.path.join(self.tmp, cover_rel), "JPEG"
        )
        source.cover_path = cover_rel
        source.cover_url = ""
        source.save(update_fields=["cover_path", "cover_url"])
        return source

    def test_cover_min_hash_matches_backfill(self):
        # Import-time and backfill hashing must agree, so both hash the saved
        # cover.min.webp rather than the full-size source.
        source = self._make_covered_source()
        self.assertTrue(generate_cover_min(source))
        source.refresh_from_db()
        self.assertEqual(
            source.cover_phash,
            dhash_file(os.path.join(self.tmp, source.cover_min_path)),
        )

    def test_get_cover_image_returns_local_cover_without_url(self):
        # A valid local cover with an empty cover_url must still be used; the
        # overview only needs cover_path.
        source = self._make_covered_source()
        self.assertIsNotNone(OverviewGenerator().get_cover_image(source))
