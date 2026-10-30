"""Tests for the volume cover put at the start of each volume's first chapter."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from ..services import audiobook_service as svc
from ..utils.crawler_path import ensure_crawler_on_path

ensure_crawler_on_path()
from bs4 import BeautifulSoup  # noqa: E402
from lncrawl.core import downloader  # noqa: E402
from lncrawl.models import Chapter, Volume  # noqa: E402

VOL1_URL = "https://img.example/vol1.jpg"
VOL2_URL = "https://img.example/vol2.jpg"
VOL1_FILE = hashlib.md5(VOL1_URL.encode()).hexdigest() + ".jpg"
VOL2_FILE = hashlib.md5(VOL2_URL.encode()).hexdigest() + ".jpg"


def h1(title):
    return f"<h1>{title}</h1>"


def cover_tag(name):
    return f'<img class="volume-cover" src="images/{name}" alt="{name}"/>'


def make_soup(text):
    return BeautifulSoup(f"<body>{text}</body>", "html.parser")


class VolumeCoverTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="lncrawl-volume-cover-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write_chapter(self, chapter, body, images=None, success=True, **extra):
        data = {
            "id": chapter.id,
            "title": chapter.title,
            "url": chapter.url,
            "body": body,
            "images": images or {},
            "success": success,
            **extra,
        }
        file_name = downloader._chapter_file(chapter, self.tmp)
        file_name.parent.mkdir(parents=True, exist_ok=True)
        file_name.write_text(json.dumps(data), encoding="utf-8")

    def read_chapter(self, chapter_id):
        file_name = Path(self.tmp) / "json" / f"{chapter_id:05}.json"
        return json.loads(file_name.read_text(encoding="utf-8"))

    def restore(self, chapter_id):
        """A chapter as a later crawl sees it: rebuilt from its saved file."""
        return Chapter(**self.read_chapter(chapter_id))

    def make_chapters(self, count=4):
        """Chapters 1..count, each saved with a plain body and no cover."""
        chapters = []
        for number in range(1, count + 1):
            chapter = Chapter(
                id=number,
                title=f"Chapter {number}",
                url=f"https://site.example/{number}",
                success=True,
            )
            self.write_chapter(chapter, h1(chapter.title) + f"<p>Text {number}</p>")
            chapters.append(chapter)
        return chapters

    def make_app(self, chapters, volumes):
        return SimpleNamespace(
            output_path=self.tmp,
            chapters=chapters,
            crawler=SimpleNamespace(volumes=volumes, make_soup=make_soup),
        )

    def two_volumes(self, url1=VOL1_URL, url2=VOL2_URL):
        return [
            Volume(id=1, start_chapter=1, final_chapter=2, chapter_count=2, cover_url=url1),
            Volume(id=2, start_chapter=3, final_chapter=4, chapter_count=2, cover_url=url2),
        ]

    def moved_volumes(self):
        """Volume 1 now starts at chapter 2, so chapter 1 is no longer a volume start."""
        return [
            Volume(id=1, start_chapter=2, final_chapter=3, chapter_count=2, cover_url=VOL1_URL),
            Volume(id=2, start_chapter=4, final_chapter=4, chapter_count=1, cover_url=VOL2_URL),
        ]

    def test_cover_goes_right_after_the_title_of_each_volume_start(self):
        chapters = self.make_chapters()
        app = self.make_app(chapters, self.two_volumes())

        downloader._insert_volume_covers(app)

        first = self.read_chapter(1)
        self.assertEqual(first["body"], h1("Chapter 1") + cover_tag(VOL1_FILE) + "<p>Text 1</p>")
        self.assertEqual(first["images"], {VOL1_FILE: VOL1_URL})
        self.assertEqual(first["volume_cover"], VOL1_FILE)

        third = self.read_chapter(3)
        self.assertEqual(third["body"], h1("Chapter 3") + cover_tag(VOL2_FILE) + "<p>Text 3</p>")
        self.assertEqual(third["images"], {VOL2_FILE: VOL2_URL})
        self.assertEqual(third["volume_cover"], VOL2_FILE)

        self.assertEqual(chapters[0].images, {VOL1_FILE: VOL1_URL})
        self.assertEqual(chapters[0].volume_cover, VOL1_FILE)
        self.assertEqual(chapters[2].images, {VOL2_FILE: VOL2_URL})
        self.assertEqual(chapters[2].volume_cover, VOL2_FILE)

        for number in (2, 4):
            other = self.read_chapter(number)
            self.assertEqual(other["body"], h1(f"Chapter {number}") + f"<p>Text {number}</p>")
            self.assertNotIn("volume_cover", other)
            self.assertEqual(other["images"], {})
            self.assertIsNone(chapters[number - 1].get("volume_cover"))

    def test_cover_follows_a_title_rewritten_by_beautifulsoup(self):
        chapters = self.make_chapters()
        chapters[0].title = "It's begun"
        self.write_chapter(chapters[0], h1("It's begun") + "<p>Text 1</p>")

        downloader._insert_volume_covers(self.make_app(chapters, self.two_volumes()))

        self.assertEqual(
            self.read_chapter(1)["body"],
            h1("It's begun") + cover_tag(VOL1_FILE) + "<p>Text 1</p>",
        )

    def test_cover_is_removed_when_the_novel_drops_to_one_volume(self):
        chapters = self.make_chapters()
        downloader._insert_volume_covers(self.make_app(chapters, self.two_volumes()))
        volumes = [Volume(id=1, start_chapter=1, chapter_count=4, cover_url=VOL1_URL)]

        downloader._insert_volume_covers(self.make_app(chapters, volumes))

        first = self.read_chapter(1)
        self.assertEqual(first["body"], h1("Chapter 1") + "<p>Text 1</p>")
        self.assertEqual(first["images"], {})

    def test_non_string_cover_is_ignored(self):
        chapters = self.make_chapters()
        volumes = self.two_volumes(url1=[VOL1_URL])

        downloader._insert_volume_covers(self.make_app(chapters, volumes))

        self.assertEqual(self.read_chapter(1)["images"], {})
        self.assertEqual(self.read_chapter(3)["images"], {VOL2_FILE: VOL2_URL})

    def test_second_run_does_not_rewrite(self):
        chapters = self.make_chapters()
        volumes = self.two_volumes()
        downloader._insert_volume_covers(self.make_app(chapters, volumes))

        restored = [self.restore(number) for number in range(1, 5)]
        with patch.object(downloader, "_write_chapter_json") as write:
            downloader._insert_volume_covers(self.make_app(restored, volumes))

        write.assert_not_called()
        self.assertEqual(restored[0].volume_cover, VOL1_FILE)

    def test_single_volume_gets_no_cover(self):
        chapters = self.make_chapters()
        volumes = [Volume(id=1, start_chapter=1, chapter_count=4, cover_url=VOL1_URL)]

        with patch.object(downloader, "_write_chapter_json") as write:
            downloader._insert_volume_covers(self.make_app(chapters, volumes))

        write.assert_not_called()
        self.assertEqual(self.read_chapter(1)["body"], h1("Chapter 1") + "<p>Text 1</p>")

    def test_same_url_on_all_volumes_gets_no_cover(self):
        chapters = self.make_chapters()
        volumes = self.two_volumes(url1=VOL1_URL, url2=VOL1_URL)

        with patch.object(downloader, "_write_chapter_json") as write:
            downloader._insert_volume_covers(self.make_app(chapters, volumes))

        write.assert_not_called()
        self.assertIsNone(chapters[0].get("volume_cover"))
        self.assertIsNone(chapters[2].get("volume_cover"))

    def test_cover_already_inline_is_not_repeated(self):
        body = h1("Chapter 3") + f'<p><img src="images/{VOL2_FILE}" alt="{VOL2_FILE}"/></p>'
        chapters = self.make_chapters()
        self.write_chapter(chapters[2], body, images={VOL2_FILE: VOL2_URL})
        app = self.make_app(chapters, self.two_volumes())

        downloader._insert_volume_covers(app)

        third = self.read_chapter(3)
        self.assertEqual(third["body"], body)
        self.assertEqual(third["images"], {VOL2_FILE: VOL2_URL})
        self.assertEqual(third["volume_cover"], VOL2_FILE)
        self.assertNotIn("volume-cover", third["body"])

    def test_cover_moved_to_another_chapter_leaves_the_old_one(self):
        chapters = self.make_chapters()
        self.write_chapter(
            chapters[0],
            h1("Chapter 1") + cover_tag(VOL1_FILE) + "<p>Text 1</p>",
            images={VOL1_FILE: VOL1_URL},
            volume_cover=VOL1_FILE,
        )
        restored = self.restore(1)
        app = self.make_app([restored, *chapters[1:]], self.moved_volumes())

        downloader._insert_volume_covers(app)

        first = self.read_chapter(1)
        self.assertEqual(first["body"], h1("Chapter 1") + "<p>Text 1</p>")
        self.assertEqual(first["images"], {})
        self.assertIsNone(first["volume_cover"])
        self.assertNotIn(VOL1_FILE, restored.images)
        self.assertIsNone(restored.volume_cover)

        second = self.read_chapter(2)
        self.assertEqual(second["body"], h1("Chapter 2") + cover_tag(VOL1_FILE) + "<p>Text 2</p>")
        self.assertEqual(second["volume_cover"], VOL1_FILE)

    def test_moved_cover_kept_on_old_chapter_when_inline_there(self):
        chapters = self.make_chapters()
        inline = f'<p><img src="images/{VOL1_FILE}" alt="{VOL1_FILE}"/></p>'
        self.write_chapter(
            chapters[0],
            h1("Chapter 1") + cover_tag(VOL1_FILE) + inline,
            images={VOL1_FILE: VOL1_URL},
            volume_cover=VOL1_FILE,
        )
        restored = self.restore(1)

        downloader._insert_volume_covers(self.make_app([restored, *chapters[1:]], self.moved_volumes()))

        first = self.read_chapter(1)
        self.assertEqual(first["body"], h1("Chapter 1") + inline)
        self.assertEqual(first["images"], {VOL1_FILE: VOL1_URL})
        self.assertIsNone(first["volume_cover"])

    def test_known_start_with_unknown_cover_keeps_its_cover(self):
        chapters = self.make_chapters()
        self.write_chapter(
            chapters[2],
            h1("Chapter 3") + cover_tag(VOL2_FILE) + "<p>Text 3</p>",
            images={VOL2_FILE: VOL2_URL},
            volume_cover=VOL2_FILE,
        )
        restored = self.restore(3)
        app = self.make_app([chapters[0], chapters[1], restored, chapters[3]], self.two_volumes(url1=None, url2=None))

        with patch.object(downloader, "_write_chapter_json") as write:
            downloader._insert_volume_covers(app)

        write.assert_not_called()
        self.assertEqual(restored.volume_cover, VOL2_FILE)
        self.assertEqual(self.read_chapter(3)["volume_cover"], VOL2_FILE)

    def test_failed_chapter_is_skipped(self):
        chapters = self.make_chapters()
        chapters[0].success = False
        self.write_chapter(chapters[0], "<p><i>Failed to download chapter body</i></p>", success=False)

        with patch.object(downloader, "_write_chapter_json") as write:
            downloader._insert_volume_covers(self.make_app(chapters, self.two_volumes()))

        write.assert_called_once()
        self.assertEqual(write.call_args.args[1].name, "00003.json")
        self.assertNotIn("volume_cover", self.read_chapter(1))

    def test_failed_cover_is_removed_then_inserted_again(self):
        chapters = self.make_chapters()
        app = self.make_app(chapters, self.two_volumes())
        downloader._insert_volume_covers(app)

        downloader._discard_failed_images(app, chapters[0], {VOL1_FILE})

        first = self.read_chapter(1)
        self.assertEqual(first["body"], h1("Chapter 1") + "<p>Text 1</p>")
        self.assertEqual(first["images"], {})
        self.assertNotIn("volume_cover", first)
        self.assertIsNone(chapters[0].volume_cover)

        downloader._insert_volume_covers(app)

        again = self.read_chapter(1)
        self.assertEqual(again["body"], h1("Chapter 1") + cover_tag(VOL1_FILE) + "<p>Text 1</p>")
        self.assertEqual(again["volume_cover"], VOL1_FILE)


class ContentHashVolumeCoverTests(SimpleTestCase):
    def test_cover_pattern_matches_the_downloader(self):
        self.assertEqual(svc._VOLUME_COVER_RE.pattern, downloader.VOLUME_COVER_RE.pattern)

    def test_inserted_cover_does_not_change_the_hash(self):
        chapters = [SimpleNamespace(chapter_id=1)]
        with patch.object(svc, "_chapter_body", return_value=h1("Chapter 1") + "<p>Text 1</p>"):
            before = svc.content_hash(chapters)

        with patch.object(svc, "_chapter_body", return_value=h1("Chapter 1") + cover_tag(VOL1_FILE) + "<p>Text 1</p>"):
            self.assertEqual(svc.content_hash(chapters), before)

        with patch.object(svc, "_chapter_body", return_value=h1("Chapter 1") + "<p>Text 1 edited</p>"):
            self.assertNotEqual(svc.content_hash(chapters), before)
