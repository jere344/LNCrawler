import os
import re
import json
import shutil
import uuid
from epub_parser import EpubParser


import re
import unicodedata


def novel_naming_rules(text: str) -> str:
    # Will be removed if they are at the end of the string
    end_remove = [
        "manga",
        "complete",
        "completed",
        "ongoing",
    ]
    for word in end_remove:
        if text.lower().endswith(word):
            text = text[: -len(word)].strip()
        if text.lower().endswith("(" + word + ")"):
            text = text[: -len(word) - 2].strip()

    # will be replaced if they are at the end of the string
    end_replace = {
        "web novel": "webnovel",
        "wn": "webnovel",
        "light novel": "lightnovel",
        "ln": "lightnovel",
    }
    for word, replacement in end_replace.items():
        if text.lower().endswith(word):
            text = text[: -len(word)].strip() + replacement 
        if text.lower().endswith("(" + word + ")"):
            text = text[: -len(word) - 2].strip() + replacement

    return text
   

def sanitize(text: str) -> str:
    """
    Remove all special characters from a string, replace accentuated characters with their
    non-accentuated counterparts, and remove all non-alphanumeric characters.
    """
    # replace all special characters with a space
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ").replace("-", " ").replace("_", " ")

    # replace common foreign characters with their english counterparts
    text = text.replace("’", "'").replace("“", '"').replace("”", '"').strip()

    # Normalize the string to decompose characters (e.g., é -> e + ´)
    text = unicodedata.normalize("NFKD", text)
    text = "".join([c for c in text if not unicodedata.combining(c)])
    
    # Remove characters that are invalid for filenames
    text = re.sub(r'[\\/:*?"<>|]', '', text)
    
    # Collapse multiple spaces into one
    text = re.sub(r'\s+', ' ', text).strip()

    # remove trailing . (windows delete silently the trailing . when renaming)
    text = text.rstrip(".")

    # Remove leading and trailing spaces
    text = text.strip()

    return text


# EPUB namespaces
NAMESPACES = {
    'opf': 'http://www.idpf.org/2007/opf',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'ncx': 'http://www.daisy.org/z3986/2005/ncx/'
}


class MultiEpubParser:
    """Class for parsing multiple EPUB files into a single novel structure"""
    
    def __init__(self, input_dir, output_path):
        self.input_dir = input_dir
        self.output_path = output_path
        self.temp_dir = os.path.join(input_dir, f"temp_multi_extract_{uuid.uuid4().hex}")
        self.epub_files = []
        self.base_output = None
        self.series_title = None
    
    def find_epub_files(self):
        """Find all EPUB files in the input directory and its subdirectories"""
        epub_files = []
        
        # Walk through all directories recursively
        for root, dirs, files in os.walk(self.input_dir):
            for file in files:
                if file.lower().endswith('.epub'):
                    full_path = os.path.join(root, file)
                    # Extract volume number for sorting
                    volume_num = self._extract_volume_number(file)
                    epub_files.append((full_path, volume_num, file))
        
        # Sort by volume number
        epub_files.sort(key=lambda x: x[1])
        self.epub_files = epub_files
        return epub_files
    
    def _extract_volume_number(self, filename):
        """Extract volume number from filename"""
        # Try to find a volume number pattern like "volume X", "vol X", "v X", or just a number
        patterns = [
            r'volume\s*(\d+)',  # matches "volume X"
            r'book\s*(\d+)',    # matches "book X"
            r'vol\s*(\d+)',     # matches "vol X"
            r'v\s*(\d+)',       # matches "v X"
            r'(\d+)'            # matches any number
        ]
        
        filename_lower = filename.lower()
        for pattern in patterns:
            match = re.search(pattern, filename_lower)
            if match:
                return int(match.group(1))
        
        # Default to volume 1 if no volume number is found
        return 1
    
    def process(self):
        """Process all EPUB files and merge them into a single structure"""
        # Find all EPUB files
        self.find_epub_files()
        
        if not self.epub_files:
            print(f"No EPUB files found in {self.input_dir}")
            return
        
        # Make sure temp directory exists
        os.makedirs(self.temp_dir, exist_ok=True)
        
        try:
            # Extract first EPUB to get series title
            first_epub_path = self.epub_files[0][0]
            first_parser = EpubParser(first_epub_path, os.path.join(self.temp_dir, "first_vol"))
            first_parser.extract()
            first_parser.parse_metadata()
            
            # Extract series title by removing volume info
            raw_title = first_parser.metadata['title']
            # Only remove specific volume patterns, not all numbers
            self.series_title = re.sub(
                r'(?:volume|vol\.?|v\.?)\s*\d+|book\s*\d+|\s+-\s+vol(?:ume)?\.?\s*\d+', 
                '', 
                raw_title, 
                flags=re.IGNORECASE
            ).strip()
            
            # Clean up trailing delimiters like " -" or " :"
            self.series_title = re.sub(r'\s+[-:]\s*$', '', self.series_title).removesuffix("-").removesuffix(":").removesuffix(",").strip()
            
            if not self.series_title:  # If title was just the volume number
                self.series_title = raw_title
            
            # Get synopsis from first book
            synopsis = first_parser.metadata.get('synopsis')
            if not synopsis:
                synopsis = first_parser.extract_synopsis_from_prologue()
            
            # If still no synopsis, use a default one
            if not synopsis:
                synopsis = f"<p>Converted from EPUB files of {self.series_title}</p>"
            
            # Create output directory structure
            safe_series_title = novel_naming_rules(sanitize(self.series_title))
            self.base_output = os.path.join(self.output_path, safe_series_title, "LNCrawler")
            os.makedirs(os.path.join(self.base_output, "json"), exist_ok=True)
            os.makedirs(os.path.join(self.base_output, "images"), exist_ok=True)
            
            # Process each EPUB file
            all_chapters = []
            all_volumes = []
            all_authors = set()
            all_translators = set()
            all_editors = set()
            publisher = None
            language = None
            has_cover = False
            global_chapter_counter = 0
            
            for i, (epub_path, _, epub_filename) in enumerate(self.epub_files):
                # Assign sequential volume ID (starting from 1)
                volume_id = i + 1
                print(f"Processing {epub_filename} (Volume {volume_id})...")
                
                # Create a parser for this volume
                parser = EpubParser(epub_path, os.path.join(self.temp_dir, f"vol_{volume_id}"))
                parser.extract()
                parser.parse_metadata()
                chapters = parser.parse_toc()
                volume_title = parser.metadata.get('title', f"Volume {volume_id}")
                
                # Update metadata collections
                all_authors.update(parser.metadata['authors'])
                all_translators.update(parser.metadata['translators'])
                all_editors.update(parser.metadata['editors'])
                
                # Use the first valid publisher and language
                if not publisher and parser.metadata['publisher']:
                    publisher = parser.metadata['publisher']
                if not language and parser.metadata['language']:
                    language = parser.metadata['language']
                
                # Copy cover if this is the first volume with a cover
                if not has_cover and parser.metadata['cover_path'] and os.path.exists(parser.metadata['cover_path']):
                    cover_filename = "cover.jpg"
                    cover_output = os.path.join(self.base_output, cover_filename)
                    shutil.copy2(parser.metadata['cover_path'], cover_output)
                    has_cover = True
                
                # Process chapters for this volume
                processed_chapters = []
                start_chapter_id = global_chapter_counter + 1
                
                for j, chapter in enumerate(chapters):
                    # Calculate global chapter ID
                    chapter_id = global_chapter_counter + j + 1
                    chapter['id'] = chapter_id
                    
                    html_content, images = parser.extract_chapter_content(chapter)
                    
                    # Create chapter data
                    chapter_data = {
                        "id": chapter_id,
                        "url": f"local://{os.path.basename(epub_path)}/{chapter['src']}",
                        "title": chapter['title'],
                        "volume": volume_id,
                        "volume_title": volume_title,
                        "body": html_content,
                        "images": {img_name: None for img_name in images.keys()},
                        "success": True if html_content else False
                    }
                    
                    # Write chapter JSON
                    chapter_json_path = os.path.join(self.base_output, "json", f"{chapter_id:05d}.json")
                    with open(chapter_json_path, 'w', encoding='utf-8') as f:
                        json.dump(chapter_data, f, indent=4)
                    
                    # For meta.json, set body to null
                    meta_chapter = chapter_data.copy()
                    meta_chapter['body'] = None
                    processed_chapters.append(meta_chapter)
                    
                    # Copy images
                    for img_name, img_path in images.items():
                        if os.path.exists(img_path):
                            output_img_path = os.path.join(self.base_output, "images", img_name)
                            shutil.copy2(img_path, output_img_path)
                
                # Update global chapter counter
                global_chapter_counter += len(chapters)
                all_chapters.extend(processed_chapters)
                
                # Create volume information
                if processed_chapters:
                    volume = {
                        "id": volume_id,
                        "title": f"Volume {volume_id}",
                        "start_chapter": start_chapter_id,
                        "final_chapter": global_chapter_counter,
                        "chapter_count": len(processed_chapters)
                    }
                    all_volumes.append(volume)
            
            # Create meta.json
            meta_data = {
                "novel": {
                    "url": f"local://{self.input_dir}",
                    "title": safe_series_title,
                    "authors": list(all_authors),
                    "cover_url": "local://cover.jpg" if has_cover else None,
                    "chapters": sorted(all_chapters, key=lambda x: x['id']),
                    "volumes": all_volumes,
                    "is_rtl": False,
                    "synopsis": synopsis,
                    "language": language or "en",
                    "novel_tags": [],
                    "has_manga": None,
                    "has_mtl": None,
                    "language_code": [],
                    "source": "epub",
                    "editors": list(all_editors),
                    "translators": list(all_translators),
                    "status": "Unknown",
                    "original_publisher": None,
                    "english_publisher": publisher,
                    "novelupdates_url": None
                }
            }
            
            # Write meta.json
            meta_json_path = os.path.join(self.base_output, "meta.json")
            with open(meta_json_path, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, indent=4)
            
            print(f"Processed {len(self.epub_files)} EPUB files with {len(all_chapters)} total chapters")
            print(f"Output saved to: {self.base_output}")
            
        finally:
            # Clean up temp directory
            self.cleanup()
    
    def cleanup(self):
        """Clean up temporary files"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

