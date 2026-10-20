"""Placeholder cover handling: duplicate groups, removal, import block and admin page."""

import os
import random

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.urls import reverse
from PIL import Image

from ..models import ExternalSource, Novel, NovelFromSource, PlaceholderCover
from ..services.covers.duplicates import duplicate_cover_groups
from ..services.covers.placeholders import mark_placeholder
from ..services.covers.resize import generate_cover_min
from .helpers import MergeTestCase


class PlaceholderCoverTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.external = ExternalSource.objects.create(source_name="placeholder-site")

    def _novel(self, title):
        slug = title.lower()
        return Novel.objects.create(title=title, slug=slug, novel_path=slug)

    def _image(self, seed):
        # Seeded noise: each seed gives a different dHash, the same seed the same one.
        raw = random.Random(seed).randbytes(400 * 600)
        return Image.frombytes("L", (400, 600), raw).convert("RGB")

    def _covered_source(self, novel, folder, seed):
        source = self.make_source(
            novel, self.external, novel.title, f"http://site/{folder}", novel.novel_path, folder
        )
        cover_rel = os.path.join(source.source_path, "cover.jpg")
        self._image(seed).save(os.path.join(self.tmp, cover_rel), "JPEG")
        source.cover_path = cover_rel
        source.save(update_fields=["cover_path"])
        self.assertTrue(generate_cover_min(source))
        source.refresh_from_db()
        return source

    def _superuser(self):
        return get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="pw"
        )

    def _shared_cover(self):
        first = self._covered_source(self._novel("Eta"), "h1", seed=6)
        second = self._covered_source(self._novel("Theta"), "i1", seed=6)
        return first.cover_phash, [first, second]

    def test_duplicate_groups_count_distinct_novels(self):
        novel_a = self._novel("Alpha")
        same_novel_a = self._covered_source(novel_a, "a1", seed=1)
        self._covered_source(novel_a, "a2", seed=1)
        self._covered_source(self._novel("Beta"), "b1", seed=2)
        pair_b = self._covered_source(self._novel("Gamma"), "c1", seed=2)
        self._covered_source(self._novel("Delta"), "d1", seed=3)
        self._covered_source(self._novel("Epsilon"), "e1", seed=3)
        triple = self._covered_source(self._novel("Zeta"), "f1", seed=3)

        groups = list(duplicate_cover_groups())

        # One novel with 2 sources is not a placeholder; the 3-novel hash comes first.
        self.assertNotIn(same_novel_a.cover_phash, [g["cover_phash"] for g in groups])
        self.assertEqual([(g["novels"], g["sources"]) for g in groups], [(3, 3), (2, 2)])
        self.assertEqual(groups[0]["cover_phash"], triple.cover_phash)
        self.assertEqual(groups[1]["cover_phash"], pair_b.cover_phash)

    def test_mark_placeholder_removes_covers_and_keeps_others(self):
        shared_a = self._covered_source(self._novel("Beta"), "b1", seed=2)
        shared_b = self._covered_source(self._novel("Gamma"), "c1", seed=2)
        other = self._covered_source(self._novel("Delta"), "d1", seed=4)
        phash = shared_a.cover_phash
        shared_a.cover_url = "http://remote/cover.jpg"
        shared_a.save(update_fields=["cover_url"])
        shared_files = [
            os.path.join(self.tmp, rel)
            for source in (shared_a, shared_b)
            for rel in (source.cover_path, source.cover_min_path)
        ]
        self.assertTrue(all(os.path.exists(path) for path in shared_files))

        placeholder = mark_placeholder(phash)

        self.assertEqual(placeholder.removed_count, 2)
        self.assertEqual(placeholder.sample_path, f"_placeholders/{phash}.webp")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, placeholder.sample_path)))
        self.assertFalse(any(os.path.exists(path) for path in shared_files))
        for source in (shared_a, shared_b):
            source.refresh_from_db()
            self.assertIsNone(source.cover_path)
            self.assertIsNone(source.cover_min_path)
            self.assertIsNone(source.cover_phash)
            self.assertIsNone(source.cover_url)
        other.refresh_from_db()
        self.assertNotEqual(other.cover_phash, phash)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, other.cover_min_path)))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, other.cover_path)))
        self.assertNotIn(phash, [g["cover_phash"] for g in duplicate_cover_groups()])

    def test_generate_cover_min_drops_blocked_hash(self):
        reference = self._covered_source(self._novel("Eps"), "e1", seed=5)
        PlaceholderCover.objects.create(cover_phash=reference.cover_phash)

        novel = self._novel("Zeta")
        source = self.make_source(novel, self.external, "Zeta", "http://site/z1", novel.novel_path, "z1")
        cover_rel = os.path.join(source.source_path, "cover.jpg")
        self._image(5).save(os.path.join(self.tmp, cover_rel), "JPEG")
        source.cover_path = cover_rel
        source.cover_url = "http://remote/cover.jpg"
        source.save(update_fields=["cover_path", "cover_url"])

        self.assertFalse(generate_cover_min(source))

        source.refresh_from_db()
        self.assertIsNone(source.cover_path)
        self.assertIsNone(source.cover_min_path)
        self.assertIsNone(source.cover_phash)
        self.assertIsNone(source.cover_url)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, cover_rel)))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, source.source_path, "cover.min.webp")))

    def test_duplicates_page_lists_shared_hash(self):
        phash, _ = self._shared_cover()
        self.client.force_login(self._superuser())

        response = self.client.get(reverse("admin:lncrawler_api_placeholdercover_duplicates"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, phash)

    def test_duplicates_post_removes_covers_and_redirects(self):
        phash, _ = self._shared_cover()
        self.client.force_login(self._superuser())
        url = reverse("admin:lncrawler_api_placeholdercover_duplicates")

        response = self.client.post(f"{url}?min=2", {"phash": phash})

        self.assertRedirects(response, f"{url}?min=2", fetch_redirect_response=False)
        self.assertTrue(PlaceholderCover.objects.filter(cover_phash=phash).exists())
        self.assertFalse(NovelFromSource.objects.filter(cover_phash=phash).exists())

    def test_duplicates_post_rejects_invalid_hash(self):
        phash, _ = self._shared_cover()
        self.client.force_login(self._superuser())
        url = reverse("admin:lncrawler_api_placeholdercover_duplicates")

        response = self.client.post(f"{url}?min=2", {"phash": "not-a-hash"})

        self.assertRedirects(response, f"{url}?min=2", fetch_redirect_response=False)
        self.assertIn("Invalid cover hash.", [str(m) for m in get_messages(response.wsgi_request)])
        self.assertFalse(PlaceholderCover.objects.exists())
        self.assertTrue(NovelFromSource.objects.filter(cover_phash=phash).exists())

    def test_duplicates_page_denies_non_staff(self):
        phash, _ = self._shared_cover()
        user = get_user_model().objects.create_user(
            username="reader", email="reader@example.com", password="pw"
        )
        self.client.force_login(user)
        url = reverse("admin:lncrawler_api_placeholdercover_duplicates")

        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

        self.client.post(url, {"phash": phash})
        self.assertFalse(PlaceholderCover.objects.exists())
        self.assertTrue(NovelFromSource.objects.filter(cover_phash=phash).exists())
