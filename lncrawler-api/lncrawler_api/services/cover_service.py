"""Cover and overview image generation.

Extracted from the former ``generate_overview`` / ``generate_cover_min``
management commands. The logic runs automatically when a source is imported
(see ``NovelFromSource.generate_overview_image`` / ``generate_cover_min``), so
it lives here as plain callables rather than management commands.
"""

import os
import textwrap
import logging
from pathlib import Path
from typing import Optional
import html
from html.parser import HTMLParser

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

logger = logging.getLogger('lncrawler_api')


def _dhash_hex(img) -> str:
    """64-bit difference hash (dHash) as 16 hex chars, for cover matching.

    Robust to resizing/re-encoding and cheap to compare by Hamming distance.
    """
    small = img.convert('L').resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(small.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            if pixels[row * 9 + col] > pixels[row * 9 + col + 1]:
                bits |= 1 << (row * 8 + col)
    return f'{bits:016x}'


def dhash_file(path) -> str:
    """dHash of an image file on disk."""
    with Image.open(path) as img:
        return _dhash_hex(img)


class HTMLTextExtractor(HTMLParser):
    """Strip HTML tags from a synopsis string."""

    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        self.text.append(data)

    def get_text(self):
        return ' '.join(self.text)


class OverviewGenerator:
    """Renders the 1200x630 Open Graph overview image for a source."""

    FONT_DIR_NAME = 'fonts'
    OG_BANNER_FILE = 'og-image.webp'
    DEFAULT_FONT_FILE = "NotoSans-Regular.ttf"
    CJK_FONT_FILES_MAP = {
        'sc': "NotoSansSC-Regular.ttf",
        'jp': "NotoSansJP-Regular.ttf",
        'kr': "NotoSansKR-Regular.ttf",
    }
    FALLBACK_SYSTEM_FONT_NAME = "arial.ttf"

    TITLE_FONT_SIZE = 52
    AUTHOR_FONT_SIZE = 32
    SYNOPSIS_FONT_SIZE = 24
    TAG_FONT_SIZE = 20
    CHAPTER_COUNT_FONT_SIZE = 32
    SOURCE_INFO_FONT_SIZE = 24

    def __init__(self):
        self._initialize_font_paths()
        self.loaded_font_objects = {}

    def _initialize_font_paths(self):
        font_base_dir = Path(str(settings.STATIC_ROOT)) / self.FONT_DIR_NAME
        self.font_file_paths = {
            'default': font_base_dir / self.DEFAULT_FONT_FILE,
        }
        for lang_code, font_file in self.CJK_FONT_FILES_MAP.items():
            self.font_file_paths[lang_code] = font_base_dir / font_file

        if not font_base_dir.is_dir():
            logger.warning("Font directory not found: %s. Font loading may fail.", font_base_dir)
        if not self.font_file_paths['default'].exists():
            logger.warning("Default font not found: %s. Font loading may rely on fallbacks.", self.font_file_paths['default'])

    def _get_font_instance(self, text_content: str, size: int) -> ImageFont.FreeTypeFont:
        default_font_path = self.font_file_paths.get('default')

        paths_to_try = []
        if self.text_has_cjk(text_content):
            for lang_code in ['sc', 'jp', 'kr']:
                p = self.font_file_paths.get(lang_code)
                if p and p.exists():
                    paths_to_try.append(p)

        if default_font_path and default_font_path.exists():
            if default_font_path not in paths_to_try:
                paths_to_try.append(default_font_path)
        elif default_font_path:
            if default_font_path not in paths_to_try:
                paths_to_try.append(default_font_path)

        for font_path in paths_to_try:
            cache_key = (str(font_path), size)
            if cache_key in self.loaded_font_objects:
                return self.loaded_font_objects[cache_key]
            try:
                font = ImageFont.truetype(str(font_path), size)
                self.loaded_font_objects[cache_key] = font
                return font
            except OSError:
                logger.warning("Could not load font %s (size %s). Trying next.", font_path, size)
                continue

        cache_key = (self.FALLBACK_SYSTEM_FONT_NAME, size)
        if cache_key in self.loaded_font_objects:
            return self.loaded_font_objects[cache_key]
        try:
            font = ImageFont.truetype(self.FALLBACK_SYSTEM_FONT_NAME, size)
            self.loaded_font_objects[cache_key] = font
            logger.warning("Using system fallback font: %s (size %s)", self.FALLBACK_SYSTEM_FONT_NAME, size)
            return font
        except OSError:
            logger.error("System fallback font %s (size %s) also failed.", self.FALLBACK_SYSTEM_FONT_NAME, size)
            cache_key_pillow_default = ("_pillow_default_", size)
            if cache_key_pillow_default in self.loaded_font_objects:
                return self.loaded_font_objects[cache_key_pillow_default]
            pillow_font = ImageFont.load_default()
            self.loaded_font_objects[cache_key_pillow_default] = pillow_font
            logger.error("Using Pillow's built-in bitmap font. Text quality and size will be severely affected.")
            return pillow_font

    def generate_overview(self, source):
        try:
            output_dir = Path(settings.LNCRAWL_OUTPUT_PATH) / source.source_path
            output_dir.mkdir(parents=True, exist_ok=True)
            overview_path = output_dir / 'overview.jpg'

            overview_img = self.create_overview_image(source)
            overview_img.save(overview_path, 'JPEG', quality=95)

            overview_rel_path = os.path.join(source.source_path, 'overview.jpg')
            source.overview_picture_path = overview_rel_path
            source.save(update_fields=['overview_picture_path'])

            logger.info("Generated overview for: %s and updated path", source.title)
        except Exception as e:
            logger.error("Failed to generate overview for %s: %s", source.title, e)

    def create_overview_image(self, source) -> Image.Image:
        width, height = 1200, 630

        img = Image.new('RGB', (width, height), (20, 25, 35))

        cover_img = self.get_cover_image(source)

        if cover_img:
            bg = self.create_background(cover_img, width, height)
            img.paste(bg, (0, 0))
        else:
            # No usable cover: fall back to the branded OG banner so the
            # overview still renders instead of a flat dark box.
            banner = self.load_og_banner(width, height)
            if banner:
                img.paste(banner, (0, 0))

        overlay = self.create_gradient_overlay(width, height)
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')

        if cover_img:
            self.add_cover_element(img, cover_img)

        draw = ImageDraw.Draw(img)
        self.add_text_content(draw, source, width, height, cover_img is not None)

        return img

    def load_og_banner(self, width: int, height: int) -> Optional[Image.Image]:
        """Load the bundled OG banner, cover-fitted to the overview canvas."""
        banner_path = Path(str(settings.STATIC_ROOT)) / self.OG_BANNER_FILE
        if not banner_path.exists():
            logger.warning("OG banner not found at %s", banner_path)
            return None
        try:
            banner = Image.open(banner_path)
            if banner.mode != 'RGB':
                banner = banner.convert('RGB')
            scale = max(width / banner.width, height / banner.height)
            banner = banner.resize(
                (int(banner.width * scale), int(banner.height * scale)),
                Image.Resampling.LANCZOS,
            )
            left = (banner.width - width) // 2
            top = (banner.height - height) // 2
            return banner.crop((left, top, left + width, top + height))
        except Exception as e:
            logger.error("Failed to load OG banner: %s", e)
            return None

    def get_cover_image(self, source) -> Optional[Image.Image]:
        if not source.cover_path:
            return None
        file_path = Path(settings.LNCRAWL_OUTPUT_PATH) / source.cover_path
        if not file_path.exists():
            return None
        try:
            cover_img = Image.open(file_path)
            if cover_img.mode != 'RGB':
                cover_img = cover_img.convert('RGB')
            return cover_img
        except Exception as e:
            logger.error("Failed to load cover image for %s: %s", source.title, e)
            return None

    def create_background(self, cover_img: Image.Image, width: int, height: int) -> Image.Image:
        cover_aspect = cover_img.width / cover_img.height
        target_aspect = width / height

        if cover_aspect > target_aspect:
            new_height = height
            new_width = int(height * cover_aspect)
        else:
            new_width = width
            new_height = int(width / cover_aspect)

        bg = cover_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        left = (new_width - width) // 2
        top = (new_height - height) // 2
        bg = bg.crop((left, top, left + width, top + height))

        bg = bg.filter(ImageFilter.GaussianBlur(radius=10))

        enhancer = ImageEnhance.Color(bg)
        bg = enhancer.enhance(1.2)

        enhancer = ImageEnhance.Contrast(bg)
        bg = enhancer.enhance(1.1)

        enhancer = ImageEnhance.Brightness(bg)
        bg = enhancer.enhance(0.5)

        return bg

    def create_gradient_overlay(self, width: int, height: int) -> Image.Image:
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        for i in range(width // 2):
            opacity = int(150 * (1 - i / (width // 2)))
            draw.line([(i, 0), (i, height)], fill=(0, 0, 0, opacity))

        return overlay

    def add_text_content(self, draw: ImageDraw.Draw, source, width: int, height: int, has_cover: bool):
        if has_cover:
            left_margin = 50
            text_width = width // 2
        else:
            left_margin = 80
            text_width = width - 160

        current_y = 80

        title_font = self._get_font_instance(source.title, self.TITLE_FONT_SIZE)
        title_lines = textwrap.wrap(source.title, width=25 if has_cover else 35)
        for line in title_lines[:3]:
            draw.text((left_margin, current_y), line, fill=(255, 255, 255), font=title_font)
            current_y += 50

        current_y += 10

        if source.authors:
            author_names = ", ".join([a.name for a in source.authors.all()])
            author_text = f"by {author_names}"
            author_font = self._get_font_instance(author_text, self.AUTHOR_FONT_SIZE)
            draw.text((left_margin, current_y), author_text, fill=(220, 220, 220), font=author_font)
            current_y += 60

        chapter_count = source.chapters_count
        chapter_text = f"{chapter_count} chapter{'s' if chapter_count != 1 else ''}"
        chapter_count_font = self._get_font_instance(chapter_text, self.CHAPTER_COUNT_FONT_SIZE)
        draw.text((left_margin, current_y), chapter_text, fill=(180, 200, 255), font=chapter_count_font)
        current_y += 40

        if hasattr(source, 'tags') and source.tags.exists():
            current_x = left_margin

            for tag in source.tags.all()[:8]:
                tag_text = tag.name
                tag_font_obj = self._get_font_instance(tag_text, self.TAG_FONT_SIZE)
                tag_width = tag_font_obj.getbbox(tag_text)[2] + 20

                if current_x + tag_width > left_margin + text_width:
                    current_x = left_margin
                    current_y += 35

                tag_bg = (60, 100, 140, 180)
                text_color = (240, 240, 240)

                self.draw_rounded_rectangle(
                    draw,
                    (current_x, current_y, current_x + tag_width, current_y + 26),
                    10,
                    tag_bg
                )

                draw.text((current_x + 10, current_y + 2), tag_text, fill=text_color, font=tag_font_obj)

                current_x += tag_width + 10

            current_y += 45

        if source.synopsis:
            parser = HTMLTextExtractor()
            parser.feed(html.unescape(source.synopsis))
            clean_synopsis = parser.get_text().strip()

            synopsis_font = self._get_font_instance(clean_synopsis, self.SYNOPSIS_FONT_SIZE)
            synopsis_lines = textwrap.wrap(clean_synopsis, width=60 if has_cover else 80)

            for line in synopsis_lines[:6]:
                if current_y > height - 100:
                    break
                draw.text((left_margin, current_y), line, fill=(200, 200, 200), font=synopsis_font)
                current_y += 30

        source_text = f"More on {settings.SITE_URL}/"
        source_info_font = self._get_font_instance(source_text, self.SOURCE_INFO_FONT_SIZE)
        draw.text((left_margin + 60, height - 60), source_text, fill=(150, 150, 150), font=source_info_font)

    def add_cover_element(self, img: Image.Image, cover_img: Image.Image):
        img_width, img_height = img.size

        cover_height = int(img_height * 0.7)
        cover_width = int(cover_height * (cover_img.width / cover_img.height))

        if cover_width > img_width * 0.4:
            cover_width = int(img_width * 0.4)
            cover_height = int(cover_width * (cover_img.height / cover_img.width))

        cover_resized = cover_img.resize((cover_width, cover_height), Image.Resampling.LANCZOS)

        x = img.width - cover_width - 80
        y = (img.height - cover_height) // 2

        shadow = Image.new('RGBA', (cover_width + 20, cover_height + 20), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rectangle((10, 10, cover_width + 10, cover_height + 10), fill=(0, 0, 0, 100))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=10))

        img.paste(shadow, (x - 5, y - 5), shadow)

        border = Image.new('RGBA', (cover_width + 6, cover_height + 6), (255, 255, 255, 120))
        border_draw = ImageDraw.Draw(border)
        border_draw.rectangle((3, 3, cover_width + 3, cover_height + 3), fill=(0, 0, 0, 0))

        img.paste(border, (x - 3, y - 3), border)
        img.paste(cover_resized, (x, y))

    def draw_rounded_rectangle(self, draw, xy, radius, color):
        upper_left_point = xy[0], xy[1]
        bottom_right_point = xy[2], xy[3]

        draw.rectangle(
            [upper_left_point[0], upper_left_point[1] + radius,
             bottom_right_point[0], bottom_right_point[1] - radius],
            fill=color
        )

        draw.rectangle(
            [upper_left_point[0] + radius, upper_left_point[1],
             bottom_right_point[0] - radius, bottom_right_point[1]],
            fill=color
        )

        draw.ellipse([upper_left_point[0], upper_left_point[1],
                     upper_left_point[0] + radius * 2, upper_left_point[1] + radius * 2],
                    fill=color)
        draw.ellipse([bottom_right_point[0] - radius * 2, upper_left_point[1],
                     bottom_right_point[0], upper_left_point[1] + radius * 2],
                    fill=color)
        draw.ellipse([upper_left_point[0], bottom_right_point[1] - radius * 2,
                     upper_left_point[0] + radius * 2, bottom_right_point[1]],
                    fill=color)
        draw.ellipse([bottom_right_point[0] - radius * 2, bottom_right_point[1] - radius * 2,
                     bottom_right_point[0], bottom_right_point[1]],
                    fill=color)

    def text_has_cjk(self, text):
        if not text:
            return False
        for char in text:
            if ord(char) > 127:
                return True
        return False


def generate_overview(source) -> bool:
    """Generate the overview image for ``source``; update its DB path field."""
    try:
        OverviewGenerator().generate_overview(source)
        return True
    except Exception as e:
        logger.error("Error generating overview image for %s: %s", source.title, e)
        return False


def generate_cover_min(source, width=200, height=300, quality=80) -> bool:
    """Generate the miniature WebP cover for ``source``."""
    try:
        if not source.cover_path:
            logger.warning("No cover image for: %s", source.title)
            return False

        cover_full_path = Path(settings.LNCRAWL_OUTPUT_PATH) / source.cover_path

        if not cover_full_path.exists():
            logger.warning("Cover image not found at: %s", cover_full_path)
            return False

        output_dir = Path(settings.LNCRAWL_OUTPUT_PATH) / source.source_path
        output_dir.mkdir(parents=True, exist_ok=True)

        cover_min_filename = 'cover.min.webp'
        cover_min_path = output_dir / cover_min_filename

        with Image.open(cover_full_path) as img:
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGB')

            img_width, img_height = img.size
            aspect_ratio = img_width / img_height

            if aspect_ratio > (width / height):
                new_width = width
                new_height = int(width / aspect_ratio)
            else:
                new_height = height
                new_width = int(height * aspect_ratio)

            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            img_resized.save(cover_min_path, 'WEBP', quality=quality)

        # Hash the saved thumbnail (not the full-size source) so import-time and
        # backfill hashes are identical and therefore comparable.
        cover_phash = dhash_file(cover_min_path)

        relative_min_path = os.path.join(source.source_path, cover_min_filename)
        source.cover_min_path = relative_min_path
        source.cover_phash = cover_phash
        source.save(update_fields=['cover_min_path', 'cover_phash'])

        logger.info("Generated miniature cover for: %s", source.title)
        return True
    except Exception as e:
        logger.error("Failed to generate miniature cover for %s: %s", source.title, e)
        return False
