"""The source image gallery: chapter images, the overview picture, and paging."""

import os

from django.urls import reverse

from ..models import Chapter, ExternalSource, NovelFromSource
from .helpers import MergeTestCase, make_novel


class SourceGalleryTests(MergeTestCase):
    def setUp(self):
        super().setUp()
        self.novel = make_novel("Gallery", "gallery")
        self.source = self.make_source(
            self.novel,
            ExternalSource.objects.create(source_name="site"),
            title="Gallery",
            url="http://gallery/1",
            novel_folder="gallery",
            source_folder="site",
            chapters=3,
        )
        Chapter.objects.filter(novel_from_source=self.source, chapter_id=1).update(
            title="", images=["a.jpg", "b.jpg"]
        )
        Chapter.objects.filter(novel_from_source=self.source, chapter_id=3).update(
            title="Chapter 3", images=["c.jpg"]
        )
        for name in ["a.jpg", "b.jpg", "c.jpg"]:
            self.write_file(os.path.join("gallery", "site", "images", name))

    def write_file(self, relative):
        path = os.path.join(self.tmp, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"img")

    def get_gallery(self, **params):
        url = reverse("source_image_gallery", kwargs={"novel_slug": "gallery", "source_slug": "site"})
        return self.client.get(url, params)

    def test_lists_chapter_images_in_chapter_order(self):
        response = self.get_gallery()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(
            [image["image_name"] for image in response.data["images"]],
            ["a.jpg", "b.jpg", "c.jpg"],
        )
        self.assertEqual(response.data["images"][0]["chapter_display_title"], "Chapter 1")

    def test_overview_picture_is_listed_first(self):
        self.source.overview_picture_file = "overview.png"
        self.source.save(update_fields=["overview_picture_file"])
        self.write_file("gallery/site/overview.png")
        response = self.get_gallery()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 4)
        self.assertEqual(response.data["images"][0]["image_name"], "overview.png")

    def test_overview_path_without_a_file_is_not_counted(self):
        self.source.overview_picture_file = "missing.png"
        self.source.save(update_fields=["overview_picture_file"])
        response = self.get_gallery()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)

    def test_second_page_with_small_page_size(self):
        response = self.get_gallery(page=2, page_size=2)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_pages"], 2)
        self.assertEqual(response.data["current_page"], 2)
        self.assertEqual([image["image_name"] for image in response.data["images"]], ["c.jpg"])

    def test_non_numeric_page_is_the_first_page(self):
        response = self.get_gallery(page="abc")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["current_page"], 1)

    def test_source_without_a_source_path_does_not_500(self):
        NovelFromSource.objects.filter(pk=self.source.pk).update(source_folder=None)
        response = self.get_gallery()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["images"], [])
