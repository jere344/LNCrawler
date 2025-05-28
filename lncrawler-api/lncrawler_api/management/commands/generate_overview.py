import os
import textwrap
from pathlib import Path
from typing import Optional
import html
from html.parser import HTMLParser
from django.core.management.base import BaseCommand
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

from ...models import NovelFromSource


# HTML Parser to strip HTML tags
class HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
    
    def handle_data(self, data):
        self.text.append(data)
    
    def get_text(self):
        return ' '.join(self.text)


class Command(BaseCommand):
    help = 'Generate overview images for sources'

    # Font configuration
    FONT_DIR_NAME = 'fonts'
    DEFAULT_FONT_FILE = "NotoSans-Regular.ttf"
    CJK_FONT_FILES_MAP = {
        'sc': "NotoSansSC-Regular.ttf",
        'jp': "NotoSansJP-Regular.ttf",
        'kr': "NotoSansKR-Regular.ttf",
    }
    FALLBACK_SYSTEM_FONT_NAME = "arial.ttf"

    # Font sizes (consistent with original)
    TITLE_FONT_SIZE = 52
    AUTHOR_FONT_SIZE = 32
    SYNOPSIS_FONT_SIZE = 24
    TAG_FONT_SIZE = 20
    CHAPTER_COUNT_FONT_SIZE = 32 # Matches author font size in original
    SOURCE_INFO_FONT_SIZE = 24   # Matches synopsis font size in original

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initialize_font_paths()
        self.loaded_font_objects = {}  # Cache: (font_identifier_str, size) -> ImageFont object

    def _initialize_font_paths(self):
        static_root_path = Path(str(settings.STATIC_ROOT))
        self.font_base_dir = static_root_path / self.FONT_DIR_NAME
        
        self.font_file_paths = {
            'default': self.font_base_dir / self.DEFAULT_FONT_FILE,
        }
        for lang_code, font_file in self.CJK_FONT_FILES_MAP.items():
            self.font_file_paths[lang_code] = self.font_base_dir / font_file

        # Initial check for font directory and default font for early warning
        if not self.font_base_dir.is_dir():
            self.stdout.write(self.style.WARNING(f"Font directory not found: {self.font_base_dir}. Font loading may fail."))
        if not self.font_file_paths['default'].exists():
            self.stdout.write(self.style.WARNING(f"Default font not found: {self.font_file_paths['default']}. Font loading may rely on fallbacks."))

    def _get_font_instance(self, text_content: str, size: int) -> ImageFont.FreeTypeFont:
        font_path_candidates = []

        if self.text_has_cjk(text_content):
            cjk_preference_order = ['sc', 'jp', 'kr']
            for lang_code in cjk_preference_order:
                path = self.font_file_paths.get(lang_code)
                if path and path.exists():
                    font_path_candidates.append(path)
        
        default_font_path = self.font_file_paths.get('default')
        if default_font_path: # Always add default font path
            font_path_candidates.append(default_font_path)
        
        # Remove duplicates while preserving order (e.g. if default was already added via CJK list if one was missing)
        # More direct: ensure default is tried if CJK specific ones fail or are not applicable.
        # The list `font_path_candidates` will contain existing CJK fonts (if applicable)
        # followed by the default font.
        
        # Revised candidate list logic:
        paths_to_try = []
        if self.text_has_cjk(text_content):
            for lang_code in ['sc', 'jp', 'kr']: # Preferred CJK order
                p = self.font_file_paths.get(lang_code)
                if p and p.exists():
                    paths_to_try.append(p)
        
        # Add default font if not already effectively covered or as a primary choice
        if default_font_path and default_font_path.exists():
            if default_font_path not in paths_to_try:
                 paths_to_try.append(default_font_path)
        elif default_font_path: # If default_font_path is configured but doesn't exist
            # Add it so the warning for this specific path can be triggered if attempted
            if default_font_path not in paths_to_try:
                paths_to_try.append(default_font_path)


        # Try loading from candidate paths
        for font_path in paths_to_try:
            cache_key = (str(font_path), size)
            if cache_key in self.loaded_font_objects:
                return self.loaded_font_objects[cache_key]
            try:
                font = ImageFont.truetype(str(font_path), size)
                self.loaded_font_objects[cache_key] = font
                return font
            except OSError:
                self.stdout.write(self.style.WARNING(f"Could not load font {font_path} (size {size}). Trying next."))
                continue
        
        # If all specified fonts fail, try system fallback font
        cache_key = (self.FALLBACK_SYSTEM_FONT_NAME, size)
        if cache_key in self.loaded_font_objects:
            return self.loaded_font_objects[cache_key]
        try:
            font = ImageFont.truetype(self.FALLBACK_SYSTEM_FONT_NAME, size)
            self.loaded_font_objects[cache_key] = font
            self.stdout.write(self.style.SUCCESS(f"Using system fallback font: {self.FALLBACK_SYSTEM_FONT_NAME} (size {size})"))
            return font
        except OSError:
            self.stdout.write(self.style.ERROR(f"System fallback font {self.FALLBACK_SYSTEM_FONT_NAME} (size {size}) also failed."))
            # Final fallback: Pillow's built-in bitmap font
            cache_key_pillow_default = ("_pillow_default_", size) 
            if cache_key_pillow_default in self.loaded_font_objects:
                return self.loaded_font_objects[cache_key_pillow_default]
            
            pillow_font = ImageFont.load_default() # Note: size is not applicable here
            self.loaded_font_objects[cache_key_pillow_default] = pillow_font
            self.stdout.write(self.style.ERROR("Using Pillow's built-in bitmap font. Text quality and size will be severely affected."))
            return pillow_font

    def add_arguments(self, parser):
        parser.add_argument(
            '--source-id',
            type=str,
            help='Generate overview for specific source ID'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Generate overview for all sources'
        )

    def handle(self, *args, **options):
        if options['source_id']:
            try:
                novel = NovelFromSource.objects.get(id=options['source_id'])
                self.generate_overview(novel)
            except NovelFromSource.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Novel with ID {options["source_id"]} not found')
                )
        elif options['all']:
            novels = NovelFromSource.objects.all()
            for novel in novels:
                self.generate_overview(novel)
        else:
            self.stdout.write(
                self.style.ERROR('Please specify --novel-id or --all')
            )

    def generate_overview(self, source: NovelFromSource):
        try:
            # Create output directory
            output_dir = Path(settings.LNCRAWL_OUTPUT_PATH) / source.source_path
            output_dir.mkdir(parents=True, exist_ok=True)
            overview_path = output_dir / 'overview.jpg'

            # Create the overview image
            overview_img = self.create_overview_image(source)
            overview_img.save(overview_path, 'JPEG', quality=95)
            
            # Update the overview_picture_path field in the database
            overview_rel_path = os.path.join(source.source_path, 'overview.jpg')
            source.overview_picture_path = overview_rel_path
            source.save(update_fields=['overview_picture_path'])
            
            self.stdout.write(
                self.style.SUCCESS(f'Generated overview for: {source.title} and updated path')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to generate overview for {source.title}: {str(e)}')
            )

    def create_overview_image(self, source:NovelFromSource) -> Image.Image:
        # Image dimensions for OG image (1200x630 recommended)
        width, height = 1200, 630
        
        img = Image.new('RGB', (width, height), (20, 25, 35))
        
        cover_img = self.get_cover_image(source)
        
        if cover_img:
            bg = self.create_background(cover_img, width, height)
            img.paste(bg, (0, 0))
        
        overlay = self.create_gradient_overlay(width, height)
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
        
        if cover_img:
            self.add_cover_element(img, cover_img)
        
        draw = ImageDraw.Draw(img)
        self.add_text_content(draw, source, width, height, cover_img is not None)
        
        return img

    def get_cover_image(self, source:NovelFromSource) -> Optional[Image.Image]:
        if not source.cover_url:
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
            self.stdout.write(
                self.style.ERROR(f'Failed to load cover image for {source.title}: {str(e)}')
            )
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
        """Create a semi-transparent gradient overlay for better text readability"""
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Left side gradient (for text area)
        for i in range(width // 2):
            # Gradient from left side (more opaque) to center (more transparent)
            opacity = int(150 * (1 - i / (width // 2)))
            draw.line([(i, 0), (i, height)], fill=(0, 0, 0, opacity))
        
        return overlay

    def add_text_content(self, draw: ImageDraw.Draw, source:NovelFromSource, width: int, height: int, has_cover: bool):
        # Load fonts with UTF-8 support
        # Fonts are now loaded dynamically per text content and size
            
        if has_cover:
            left_margin = 50
            text_width = width // 2
        else:
            left_margin = 80
            text_width = width - 160
            
        current_y = 80
        
        # Title
        title_font = self._get_font_instance(source.title, self.TITLE_FONT_SIZE)
        title_lines = textwrap.wrap(source.title, width=25 if has_cover else 35)
        for line in title_lines[:3]:  # Max 3 lines
            draw.text((left_margin, current_y), line, fill=(255, 255, 255), font=title_font)
            current_y += 50 # Keeping fixed line heights from original for now
        
        current_y += 10
        
        # Author
        if source.authors:
            author_names = ", ".join([a.name for a in source.authors.all()])
            author_text = f"by {author_names}"
            author_font = self._get_font_instance(author_text, self.AUTHOR_FONT_SIZE)
            draw.text((left_margin, current_y), author_text, fill=(220, 220, 220), font=author_font)
            current_y += 60
        
        # Chapter count
        chapter_count = source.chapters_count
        chapter_text = f"{chapter_count} chapter{'s' if chapter_count != 1 else ''}"
        chapter_count_font = self._get_font_instance(chapter_text, self.CHAPTER_COUNT_FONT_SIZE)
        draw.text((left_margin, current_y), chapter_text, fill=(180, 200, 255), font=chapter_count_font)
        current_y += 40
        
        # Tags
        if hasattr(source, 'tags') and source.tags.exists():
            tag_y = current_y # Not used, current_y is updated directly
            current_x = left_margin
            
            # Draw tags in a flowing layout
            for i, tag in enumerate(source.tags.all()[:8]):  # Limit to 8 tags
                tag_text = tag.name
                tag_font_obj = self._get_font_instance(tag_text, self.TAG_FONT_SIZE)
                tag_width = tag_font_obj.getbbox(tag_text)[2] + 20 # width of text box + padding
                
                # Create new line if tag won't fit
                if current_x + tag_width > left_margin + text_width:
                    current_x = left_margin
                    current_y += 35
                
                # Tag background
                tag_bg = (60, 100, 140, 180)
                text_color = (240, 240, 240)
                
                # Draw rounded rectangle for tag
                self.draw_rounded_rectangle(
                    draw, 
                    (current_x, current_y, current_x + tag_width, current_y + 26),
                    10, 
                    tag_bg
                )
                
                # Draw tag text
                draw.text((current_x + 10, current_y + 2), tag_text, fill=text_color, font=tag_font_obj)
                
                # Move x position for next tag
                current_x += tag_width + 10
            
            # Move to next line after tags
            current_y += 45
        
        # Synopsis - parse HTML content
        if source.synopsis:
            # Extract plain text from HTML
            parser = HTMLTextExtractor()
            parser.feed(html.unescape(source.synopsis))
            clean_synopsis = parser.get_text().strip()
            
            synopsis_font = self._get_font_instance(clean_synopsis, self.SYNOPSIS_FONT_SIZE)
            synopsis_lines = textwrap.wrap(clean_synopsis, width=60 if has_cover else 80)
                
            for line in synopsis_lines[:6]:  # Max 6 lines
                if current_y > height - 100:  # Don't overflow
                    break
                draw.text((left_margin, current_y), line, fill=(200, 200, 200), font=synopsis_font)
                current_y += 30

        # Add source info at bottom
        source_text = f"More on {settings.SITE_URL}/" # Assuming SITE_URL does not need specific CJK font
        source_info_font = self._get_font_instance(source_text, self.SOURCE_INFO_FONT_SIZE)
        draw.text((left_margin + 60, height - 60), source_text, fill=(150, 150, 150), font=source_info_font)

    def add_cover_element(self, img: Image.Image, cover_img: Image.Image):
        # Add cover as a more prominent element on the right side
        img_width, img_height = img.size
        
        # Make cover larger - about 40% of image height
        cover_height = int(img_height * 0.7)
        cover_width = int(cover_height * (cover_img.width / cover_img.height))
        
        # Don't let it get too wide
        if cover_width > img_width * 0.4:
            cover_width = int(img_width * 0.4)
            cover_height = int(cover_width * (cover_img.height / cover_img.width))
        
        cover_resized = cover_img.resize((cover_width, cover_height), Image.Resampling.LANCZOS)
        
        # Position on right side
        x = img.width - cover_width - 80
        y = (img.height - cover_height) // 2
        
        # Create a drop shadow
        shadow = Image.new('RGBA', (cover_width + 20, cover_height + 20), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rectangle((10, 10, cover_width + 10, cover_height + 10), fill=(0, 0, 0, 100))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=10))
        
        # Paste shadow and cover
        img.paste(shadow, (x - 5, y - 5), shadow)
        
        # Create border for the cover
        border = Image.new('RGBA', (cover_width + 6, cover_height + 6), (255, 255, 255, 120))
        border_draw = ImageDraw.Draw(border)
        border_draw.rectangle((3, 3, cover_width + 3, cover_height + 3), fill=(0, 0, 0, 0))
        
        # Paste border and cover
        img.paste(border, (x - 3, y - 3), border)
        img.paste(cover_resized, (x, y))

    def draw_rounded_rectangle(self, draw, xy, radius, color):
        """Draw a rounded rectangle"""
        upper_left_point = xy[0], xy[1]
        bottom_right_point = xy[2], xy[3]
        
        # Draw rectangle
        draw.rectangle(
            [upper_left_point[0], upper_left_point[1] + radius,
             bottom_right_point[0], bottom_right_point[1] - radius],
            fill=color
        )
        
        # Draw rectangle
        draw.rectangle(
            [upper_left_point[0] + radius, upper_left_point[1],
             bottom_right_point[0] - radius, bottom_right_point[1]],
            fill=color
        )
        
        # Draw circles at corners
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
        """Check if text contains non-Latin Unicode characters (simple check)"""
        if not text:
            return False
            
        for char in text:
            # Simple check if character is not in ASCII range
            if ord(char) > 127:
                return True
        return False
