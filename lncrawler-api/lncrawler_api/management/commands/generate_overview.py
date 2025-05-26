import os
import textwrap
from pathlib import Path
from typing import Optional
import html
from html.parser import HTMLParser
import qrcode
from urllib.parse import quote

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
        
        self.add_qr_code(img, source)
        
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
        fonts = self.load_fonts()
        if not fonts:
            return
            
        title_font, author_font, synopsis_font, tag_font = fonts
        
        if has_cover:
            left_margin = 50
            text_width = width // 2
        else:
            left_margin = 80
            text_width = width - 160
            
        current_y = 80
        
        # Title
        title_lines = textwrap.wrap(source.title, width=25 if has_cover else 35)
        for line in title_lines[:3]:  # Max 3 lines
            draw.text((left_margin, current_y), line, fill=(255, 255, 255), font=title_font)
            current_y += 40
        
        current_y += 20
        
        # Author
        if source.authors:
            author_names = ", ".join([a.name for a in source.authors.all()])
            author_text = f"by {author_names}"
            draw.text((left_margin, current_y), author_text, fill=(220, 220, 220), font=author_font)
            current_y += 60
        
        # Chapter count
        chapter_count = source.chapters_count
        chapter_text = f"{chapter_count} chapter{'s' if chapter_count != 1 else ''}"
        draw.text((left_margin, current_y), chapter_text, fill=(180, 200, 255), font=author_font)
        current_y += 40
        
        # Tags
        if hasattr(source, 'tags') and source.tags.exists():
            tag_y = current_y
            current_x = left_margin
            
            # Draw tags in a flowing layout
            for i, tag in enumerate(source.tags.all()[:8]):  # Limit to 8 tags
                tag_text = tag.name
                tag_width = tag_font.getbbox(tag_text)[2] + 20
                
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
                draw.text((current_x + 10, current_y + 2), tag_text, fill=text_color, font=tag_font)
                
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
            
            synopsis_lines = textwrap.wrap(clean_synopsis, width=60 if has_cover else 80)
                
            for line in synopsis_lines[:6]:  # Max 6 lines
                if current_y > height - 100:  # Don't overflow
                    break
                draw.text((left_margin, current_y), line, fill=(200, 200, 200), font=synopsis_font)
                current_y += 30

        # Add source info at bottom
        source_text = f"More on {settings.SITE_URL}/"
        draw.text((left_margin + 100, height - 60), source_text, fill=(150, 150, 150), font=synopsis_font)

    def add_qr_code(self, img: Image.Image, source: NovelFromSource):
        """Add a more discrete QR code to the bottom left of the overview image"""
        # Generate the URL for the QR code
        url = f"{settings.SITE_API_URL}/{settings.LNCRAWL_URL}{source.cover_path}"
        safe_url = quote(url, safe=':/')
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=4,  # Smaller box size
            border=1
        )
        qr.add_data(safe_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="white", back_color="black")
        
        # Resize QR code to be smaller (80x80 pixels)
        qr_size = 80
        qr_img = qr_img.resize((qr_size, qr_size))
        
        # Convert to RGBA if needed
        if qr_img.mode != 'RGBA':
            qr_img = qr_img.convert('RGBA')

        img_width, img_height = img.size
        position = (50, img_height - qr_size - 30)
        bg = Image.new('RGBA', (qr_size + 10, qr_size + 10), (0, 0, 0, 120))
        
        qr_data = qr_img.getdata()
        new_data = []
        for item in qr_data:
            # If white, make it semi-transparent
            if item[0] > 200:  # White or near-white
                new_data.append((255, 255, 255, 180))  # Semi-transparent white
            else:
                new_data.append((0, 0, 0, 200))  # Near-opaque black
        
        qr_img.putdata(new_data)
        
        # Paste semi-transparent background
        img.paste(bg, (position[0] - 5, position[1] - 5), bg)
        
        # Paste QR code
        img.paste(qr_img, position, qr_img)

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

    def load_fonts(self):
        """Load fonts with good UTF-8 support"""
        try:
            # List of fonts with good Unicode support in order of preference
            font_options = [
                # Cross-platform fonts with good Unicode support
                "Arial Unicode MS",
                "DejaVu Sans",
                "Noto Sans",
                # Windows fonts
                "msyh.ttc",      # Microsoft YaHei (has good Unicode coverage)
                "arial.ttf",
                "segoeui.ttf",
                # Linux/macOS fonts
                "NotoSans-Regular.ttf",
            ]
            
            # Try each font until one works
            for font_name in font_options:
                try:
                    title_font = ImageFont.truetype(font_name, 52)
                    author_font = ImageFont.truetype(font_name, 32)
                    synopsis_font = ImageFont.truetype(font_name, 24)
                    tag_font = ImageFont.truetype(font_name, 20)
                    return title_font, author_font, synopsis_font, tag_font
                except OSError:
                    continue
            
            # Fallback to default font
            self.stdout.write(self.style.WARNING("Using default font"))
            title_font = ImageFont.truetype("arial.ttf", 52)
            author_font = ImageFont.truetype("arial.ttf", 32)
            synopsis_font = ImageFont.truetype("arial.ttf", 24)
            tag_font = ImageFont.truetype("arial.ttf", 20)
            return title_font, author_font, synopsis_font, tag_font
                
        except OSError:
            self.stdout.write(self.style.ERROR("Could not load any fonts"))
            return None

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
        """Check if text contains non-Latin Unicode characters"""
        if not text:
            return False
            
        for char in text:
            # Simple check if character is not in ASCII range
            if ord(char) > 127:
                return True
        return False
