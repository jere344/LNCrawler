import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from PIL import Image

from ...models import NovelFromSource


class Command(BaseCommand):
    help = 'Generate miniature WebP versions of novel covers'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source-id',
            type=str,
            help='Generate miniature cover for specific source ID'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Generate miniature covers for all sources'
        )
        parser.add_argument(
            '--width',
            type=int,
            default=200,
            help='Width of the miniature cover (default: 200)'
        )
        parser.add_argument(
            '--height',
            type=int,
            default=300,
            help='Height of the miniature cover (default: 300)'
        )
        parser.add_argument(
            '--quality',
            type=int,
            default=80,
            help='WebP quality (0-100, default: 80)'
        )

    def handle(self, *args, **options):
        if options['source_id']:
            try:
                source = NovelFromSource.objects.get(id=options['source_id'])
                self.generate_cover_min(
                    source, 
                    options['width'], 
                    options['height'],
                    options['quality']
                )
            except NovelFromSource.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Novel with ID {options["source_id"]} not found')
                )
        elif options['all']:
            sources = NovelFromSource.objects.all()
            for source in sources:
                self.generate_cover_min(
                    source, 
                    options['width'], 
                    options['height'],
                    options['quality']
                )
        else:
            self.stdout.write(
                self.style.ERROR('Please specify --source-id or --all')
            )

    def generate_cover_min(self, source: NovelFromSource, width: int = 200, height: int = 300, quality: int = 80):
        """Generate a miniature WebP version of the cover image"""
        try:
            if not source.cover_path:
                self.stdout.write(
                    self.style.WARNING(f'No cover image for: {source.title}')
                )
                return

            # Get full path to cover image
            cover_full_path = Path(settings.LNCRAWL_OUTPUT_PATH) / source.cover_path
            
            if not cover_full_path.exists():
                self.stdout.write(
                    self.style.WARNING(f'Cover image not found at: {cover_full_path}')
                )
                return

            # Create output directory if it doesn't exist
            output_dir = Path(settings.LNCRAWL_OUTPUT_PATH) / source.source_path
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Set path for the miniature WebP image
            cover_min_filename = 'cover.min.webp'
            cover_min_path = output_dir / cover_min_filename
            
            # Open and resize the cover image
            with Image.open(cover_full_path) as img:
                # Convert to RGB mode if needed (WebP requires RGB or RGBA)
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')
                
                # Calculate resize dimensions while preserving aspect ratio
                img_width, img_height = img.size
                aspect_ratio = img_width / img_height
                
                if aspect_ratio > (width / height):  # Image is wider than target
                    new_width = width
                    new_height = int(width / aspect_ratio)
                else:  # Image is taller than target
                    new_height = height
                    new_width = int(height * aspect_ratio)
                
                # Resize image
                img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Save as WebP directly without creating a white canvas
                img_resized.save(cover_min_path, 'WEBP', quality=quality)
            
            # Update the cover_min_path field in the database
            relative_min_path = os.path.join(source.source_path, cover_min_filename)
            source.cover_min_path = relative_min_path
            source.save(update_fields=['cover_min_path'])
            
            self.stdout.write(
                self.style.SUCCESS(f'Generated miniature cover for: {source.title}')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to generate miniature cover for {source.title}: {str(e)}')
            )
