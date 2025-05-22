import os
import zipfile
import shutil
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import hashlib
import uuid

# EPUB namespaces
NAMESPACES = {
    'opf': 'http://www.idpf.org/2007/opf',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'ncx': 'http://www.daisy.org/z3986/2005/ncx/'
}

class EpubParser:
    """Class for parsing a single EPUB file"""
    
    def __init__(self, epub_path, temp_dir=None):
        self.epub_path = epub_path
        self.temp_dir = temp_dir or os.path.join(os.path.dirname(epub_path), f"temp_extract_{uuid.uuid4().hex}")
        self.content_opf_path = None
        self.metadata = None
        self.chapters = None
        self.spine_order = []
        self.spine_to_file = {}
        
    def extract(self):
        """Extract the EPUB file to the temporary directory"""
        os.makedirs(self.temp_dir, exist_ok=True)
        with zipfile.ZipFile(self.epub_path, 'r') as zip_ref:
            zip_ref.extractall(self.temp_dir)
        
        # Find content.opf file
        self.content_opf_path = None
        for root, dirs, files in os.walk(self.temp_dir):
            for file in files:
                if file.endswith('content.opf') or file.endswith('package.opf') or file.endswith('volume.opf') or file.endswith('book.opf'):
                    self.content_opf_path = os.path.join(root, file)
                    break
            if self.content_opf_path:
                break
        
        return self.content_opf_path
    
    def parse_metadata(self):
        """Parse metadata from content.opf file"""
        if not self.content_opf_path:
            print("No content.opf file found.")
            return None
            
        content_dir = os.path.dirname(self.content_opf_path)
        tree = ET.parse(self.content_opf_path)
        root = tree.getroot()
        
        # Detect namespaces used in the file
        namespaces = {prefix: uri for prefix, uri in root.nsmap.items()} if hasattr(root, 'nsmap') else {}
        
        # Improved element finding that handles different namespace patterns
        def find_element(xpath, default=None):
            # Try direct find first
            element = root.find(xpath)
            if element is not None:
                return element
            
            # Try with explicit namespace
            if xpath.startswith('.//{'):
                return root.find(xpath)
            
            # Try without namespace
            simple_xpath = xpath.replace('.//{http://purl.org/dc/elements/1.1/}', './/dc:')
            simple_xpath = simple_xpath.replace('.//{http://www.idpf.org/2007/opf}', './/opf:')
            element = root.find(simple_xpath, namespaces=NAMESPACES)
            if element is not None:
                return element
            
            # Try with direct tag name as fallback
            tag_name = xpath.split('}')[-1]
            for child in root.findall('.//*'):
                if child.tag.endswith(tag_name):
                    return child
            
            return default
        
        # Get basic metadata
        title_elem = find_element('.//{http://purl.org/dc/elements/1.1/}title')
        title = title_elem.text if title_elem is not None else "Unknown Title"
        
        # Get authors, translators, editors
        authors = []
        translators = []
        editors = []
        
        creators = root.findall('.//{http://purl.org/dc/elements/1.1/}creator') or []
        if not creators:
            # Try alternative search methods
            creators = []
            for element in root.findall('.//*'):
                if element.tag.endswith('creator'):
                    creators.append(element)
        
        for creator in creators:
            creator_id = creator.get('id')
            creator_name = creator.text
            if not creator_id or not creator_name:
                continue
                
            role_elem = root.find(f'.//*[@refines="#{creator_id}"][@property="role"]')
            if role_elem is not None and role_elem.text == 'aut':
                authors.append(creator_name)
            elif role_elem is not None and role_elem.text == 'trl':
                translators.append(creator_name)
            elif role_elem is not None and role_elem.text == 'edt':
                editors.append(creator_name)
            else:
                authors.append(creator_name)
        
        # If no authors found, try to find them by other means
        if not authors:
            # Look for contributor elements
            for contrib in root.findall('.//{http://purl.org/dc/elements/1.1/}contributor') or []:
                if contrib.text and contrib.text.strip():
                    authors.append(contrib.text.strip())
            
            # If still no authors, add "Unknown Author"
            if not authors:
                authors = ["Unknown Author"]
        
        # Get language
        language_elem = find_element('.//{http://purl.org/dc/elements/1.1/}language')
        language = language_elem.text if language_elem is not None else "en"
        
        # Get publisher
        publisher_elem = find_element('.//{http://purl.org/dc/elements/1.1/}publisher')
        publisher = publisher_elem.text if publisher_elem is not None else None
        
        # Find cover image
        cover_href = None
        cover_meta = find_element('.//{http://www.idpf.org/2007/opf}meta[@name="cover"]')
        if cover_meta is not None:
            cover_id = cover_meta.get('content')
            cover_item = root.find(f'.//*[@id="{cover_id}"]')
            if cover_item is not None:
                cover_href = cover_item.get('href')
        
        if not cover_href:
            # Try finding the cover by properties
            cover_item = None
            for item in root.findall('.//*'):
                if item.get('properties') == 'cover-image':
                    cover_item = item
                    break
            if cover_item is not None:
                cover_href = cover_item.get('href')
        
        # Try finding cover based on filename patterns
        if not cover_href:
            for item in root.findall('.//*'):
                href = item.get('href')
                if href and ('cover' in href.lower() or 'title' in href.lower()) and (
                    href.lower().endswith('.jpg') or href.lower().endswith('.jpeg') or 
                    href.lower().endswith('.png')):
                    cover_href = href
                    break
        
        # Normalize cover path
        if cover_href:
            cover_path = os.path.normpath(os.path.join(content_dir, cover_href))
        else:
            cover_path = None
        
        # Find toc.ncx path
        toc_item = find_element('.//{http://www.idpf.org/2007/opf}item[@id="ncx"]')
        if toc_item is not None:
            toc_href = toc_item.get('href')
            toc_path = os.path.normpath(os.path.join(content_dir, toc_href))
        else:
            # Try finding any item with properties="nav"
            toc_item = None
            for item in root.findall('.//*'):
                if item.get('properties') == 'nav':
                    toc_item = item
                    break
            
            if toc_item is not None:
                toc_href = toc_item.get('href')
                toc_path = os.path.normpath(os.path.join(content_dir, toc_href))
            else:
                # Last resort - look for toc.ncx or toc.xhtml
                toc_path = None
                potential_toc_files = ['toc.ncx', 'toc.xhtml', 'nav.xhtml']
                for toc_file in potential_toc_files:
                    potential_path = os.path.join(content_dir, toc_file)
                    if os.path.exists(potential_path):
                        toc_path = potential_path
                        break
        
        # Get spine order
        spine = []
        for itemref in root.findall('.//{http://www.idpf.org/2007/opf}spine/{http://www.idpf.org/2007/opf}itemref') or []:
            idref = itemref.get('idref')
            if idref:
                spine.append(idref)
        
        # If no spine found using namespaces, try direct child access
        if not spine:
            spine_elem = None
            for child in root:
                if child.tag.endswith('spine'):
                    spine_elem = child
                    break
            
            if spine_elem is not None:
                for itemref in spine_elem:
                    if itemref.tag.endswith('itemref'):
                        idref = itemref.get('idref')
                        if idref:
                            spine.append(idref)
        
        # Map items to their paths
        item_paths = {}
        manifest_items = root.findall('.//{http://www.idpf.org/2007/opf}item') or []
        
        # If no items found using namespaces, try direct child access
        if not manifest_items:
            manifest_elem = None
            for child in root:
                if child.tag.endswith('manifest'):
                    manifest_elem = child
                    break
            
            if manifest_elem is not None:
                manifest_items = manifest_elem.findall('.//*')
        
        for item in manifest_items:
            item_id = item.get('id')
            item_href = item.get('href')
            if item_id and item_href:
                item_paths[item_id] = os.path.normpath(os.path.join(content_dir, item_href))
        
        # Extract synopsis from description or first chapter
        synopsis = None
        description_elem = find_element('.//{http://purl.org/dc/elements/1.1/}description')
        if description_elem is not None and description_elem.text:
            synopsis = f"<p>{description_elem.text}</p>"
        
        self.metadata = {
            'title': title,
            'authors': authors,
            'translators': translators,
            'editors': editors,
            'language': language,
            'publisher': publisher,
            'cover_path': cover_path,
            'toc_path': toc_path,
            'spine': spine,
            'item_paths': item_paths,
            'content_dir': content_dir,
            'synopsis': synopsis
        }
        
        return self.metadata
    
    def parse_toc(self):
        """Parse TOC from toc.ncx file and organize content by spine order"""
        if not self.metadata:
            return []
        
        # Extract spine order first
        self._extract_spine_order()
        
        # If we have no toc_path or it doesn't exist, create chapters based on spine
        if not self.metadata.get('toc_path') or not os.path.exists(self.metadata.get('toc_path', '')):
            print("No TOC file found. Creating chapters based on spine order.")
            return self._create_chapters_from_spine()
        
        toc_path = self.metadata['toc_path']
        # Check file extension to determine parsing approach
        if toc_path.endswith('.ncx'):
            return self._parse_ncx_toc(toc_path)
        else:  # Assume XHTML TOC (nav.xhtml or toc.xhtml)
            return self._parse_xhtml_toc(toc_path)
    
    def _parse_ncx_toc(self, toc_path):
        """Parse TOC from toc.ncx file"""
        tree = ET.parse(toc_path)
        root = tree.getroot()
        
        # Build a mapping of src paths to TOC entries
        toc_entries = {}
        nav_points = root.findall('.//{http://www.daisy.org/z3986/2005/ncx/}navPoint')
        
        # If no nav points found using namespace, try without namespace
        if not nav_points:
            for element in root.findall('.//*'):
                if element.tag.endswith('navPoint'):
                    nav_points.append(element)
        
        for i, nav_point in enumerate(nav_points):
            # Find label and content with or without namespace
            label = None
            content = None
            
            # With namespace
            label_elem = nav_point.find('.//{http://www.daisy.org/z3986/2005/ncx/}navLabel/{http://www.daisy.org/z3986/2005/ncx/}text')
            content_elem = nav_point.find('.//{http://www.daisy.org/z3986/2005/ncx/}content')
            
            # Without namespace
            if label_elem is None or content_elem is None:
                for elem in nav_point.findall('.//*'):
                    if elem.tag.endswith('text') and 'navLabel' in elem.getparent().tag:
                        label_elem = elem
                    elif elem.tag.endswith('content'):
                        content_elem = elem
            
            if label_elem is not None and content_elem is not None:
                title = label_elem.text if label_elem.text else ""
                src = content_elem.get('src')
                
                # Skip TOC, cover and other non-chapter entries in the TOC itself
                skip_keywords = ['toc', 'copyright', 'about']
                if any(keyword.lower() in title.lower() for keyword in skip_keywords):
                    continue
                
                # Normalize the src path for comparison
                normalized_src = self._normalize_src(src)
                toc_entries[normalized_src] = {
                    'title': title,
                    'src': src,
                    'index': i
                }
        
        return self._build_chapters_from_toc_entries(toc_entries)
    
    def _parse_xhtml_toc(self, toc_path):
        """Parse TOC from nav.xhtml or toc.xhtml file"""
        with open(toc_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        soup = BeautifulSoup(content, 'html.parser')
        toc_entries = {}
        
        # Find nav element with epub:type="toc" or any nav
        nav = soup.find('nav', attrs={'epub:type': 'toc'})
        if not nav:
            nav = soup.find('nav')
        
        if not nav:
            # Fallback to any div or section that might contain TOC
            nav = soup.find(['div', 'section'], class_=['toc', 'contents'])
        
        if nav:
            # Find all links in the nav
            links = nav.find_all('a')
            for i, link in enumerate(links):
                href = link.get('href')
                title = link.get_text().strip()
                
                if href and title:
                    # Skip TOC, cover and other non-chapter entries
                    skip_keywords = ['toc', 'copyright', 'about']
                    if any(keyword.lower() in title.lower() for keyword in skip_keywords):
                        continue
                    
                    # Handle fragment identifiers in href
                    if '#' in href:
                        href_parts = href.split('#')
                        href = href_parts[0]
                    
                    # Normalize the src path for comparison
                    normalized_src = self._normalize_src(href)
                    toc_entries[normalized_src] = {
                        'title': title,
                        'src': href,
                        'index': i
                    }
        
        return self._build_chapters_from_toc_entries(toc_entries)
    
    def _create_chapters_from_spine(self):
        """Create chapters based on spine order when no TOC is available"""
        print("Creating chapters from spine order")
        chapters = []
        content_dir = self.metadata['content_dir']
        
        if not self.spine_order:
            print("Warning: No spine order found")
            return chapters
        
        # Group items into chapters (each item becomes a chapter)
        for i, item_id in enumerate(self.spine_order):
            if item_id not in self.spine_to_file:
                continue
                
            filepath = self.spine_to_file[item_id]
            # Skip items with copyright in their ID
            if item_id + '_is_copyright' in self.spine_to_file:
                continue
                
            # Try to extract a title from the file
            title = f"Chapter {i+1}"
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    soup = BeautifulSoup(content, 'html.parser')
                    heading = soup.find(['h1', 'h2', 'h3', 'h4', 'title'])
                    if heading and heading.text.strip():
                        title = heading.text.strip()
            except Exception as e:
                print(f"Error reading {filepath}: {e}")
            
            chapter = {
                'id': i + 1,
                'title': title,
                'src': os.path.relpath(filepath, content_dir),
                'items': [item_id],
                'item_paths': [filepath]
            }
            chapters.append(chapter)
        
        return chapters
    
    def _build_chapters_from_toc_entries(self, toc_entries):
        """Build chapters based on TOC entries and spine order"""
        chapters = []
        current_chapter = None
        included_items = set()
        content_dir = self.metadata['content_dir']
        
        # Find the first TOC entry in the spine (e.g., prologue or chapter 1)
        first_toc_entry = None
        first_toc_spine_idx = -1
        
        for spine_idx, item_id in enumerate(self.spine_order):
            if item_id not in self.spine_to_file:
                continue
                
            filepath = self.spine_to_file[item_id]
            rel_path = os.path.relpath(filepath, content_dir)
            normalized_path = self._normalize_src(rel_path)
            
            if normalized_path in toc_entries:
                first_toc_entry = toc_entries[normalized_path]
                first_toc_spine_idx = spine_idx
                break
        # If we found a TOC entry, create chapters
        if first_toc_entry:
            # Create the first chapter and include all preceding content
            first_chapter = {
                'id': 1,
                'title': first_toc_entry['title'],
                'src': first_toc_entry['src'],
                'items': [],
                'item_paths': []
            }
            
            # Add all content from the start of the spine up to this first TOC entry
            for i in range(first_toc_spine_idx + 1):  # +1 to include the first TOC entry itself
                item_id = self.spine_order[i]
                if item_id in self.spine_to_file:
                    filepath = self.spine_to_file[item_id]
                    # Skip copyright pages
                    if item_id + '_is_copyright' in self.spine_to_file:
                        continue
                    
                    first_chapter['items'].append(item_id)
                    first_chapter['item_paths'].append(filepath)
                    included_items.add(item_id)
            
            chapters.append(first_chapter)
            current_chapter = first_chapter
            
            # Process the rest of the spine items
            for spine_idx in range(first_toc_spine_idx + 1, len(self.spine_order)):
                item_id = self.spine_order[spine_idx]
                if item_id not in self.spine_to_file:
                    continue
                
                filepath = self.spine_to_file[item_id]
                rel_path = os.path.relpath(filepath, content_dir)
                normalized_path = self._normalize_src(rel_path)
                
                # Skip copyright pages
                if item_id + '_is_copyright' in self.spine_to_file:
                    continue
                
                # If this item is in the TOC, start a new chapter
                if normalized_path in toc_entries and normalized_path != self._normalize_src(first_toc_entry['src']):
                    toc_entry = toc_entries[normalized_path]
                    
                    # Start a new chapter
                    current_chapter = {
                        'id': len(chapters) + 1,
                        'title': toc_entry['title'],
                        'src': toc_entry['src'],
                        'items': [item_id],
                        'item_paths': [filepath]
                    }
                    chapters.append(current_chapter)
                    included_items.add(item_id)
                # Otherwise, add to current chapter
                elif current_chapter:
                    current_chapter['items'].append(item_id)
                    current_chapter['item_paths'].append(filepath)
                    included_items.add(item_id)
        
        # If we have no chapters, create a single chapter with all content
        if not chapters:
            return self._create_chapters_from_spine()
        
        return chapters
    
    def _extract_spine_order(self):
        """Extract the spine order from content.opf"""
        if not self.content_opf_path:
            return
        
        tree = ET.parse(self.content_opf_path)
        root = tree.getroot()
        content_dir = os.path.dirname(self.content_opf_path)
        
        # Build a mapping of ids to file paths
        manifest_items = root.findall('.//{http://www.idpf.org/2007/opf}item')
        
        # If no items found using namespaces, try direct child access
        if not manifest_items:
            manifest_elem = None
            for child in root:
                if child.tag.endswith('manifest'):
                    manifest_elem = child
                    break
            
            if manifest_elem is not None:
                manifest_items = manifest_elem.findall('.//*')
        
        for item in manifest_items:
            item_id = item.get('id')
            href = item.get('href')
            if item_id and href:
                # Resolve the full path
                full_path = os.path.normpath(os.path.join(content_dir, href))
                self.spine_to_file[item_id] = full_path
                
                # Flag copyright pages by ID for better detection
                if 'copyright' in item_id.lower() or 'copyright' in href.lower():
                    self.spine_to_file[item_id + '_is_copyright'] = True
    
        # Get the spine order
        self.spine_order = []
        spine_items = root.findall('.//{http://www.idpf.org/2007/opf}spine/{http://www.idpf.org/2007/opf}itemref')
        
        # If no spine items found using namespaces, try direct child access
        if not spine_items:
            spine_elem = None
            for child in root:
                if child.tag.endswith('spine'):
                    spine_elem = child
                    break
            
            if spine_elem is not None:
                spine_items = spine_elem.findall('.//*')
                if not spine_items:  # Try direct children
                    spine_items = list(spine_elem)
        
        for itemref in spine_items:
            idref = itemref.get('idref')
            if idref:
                self.spine_order.append(idref)
    
    def _normalize_src(self, src):
        """Normalize a source path for comparison"""
        # Remove fragment identifiers and normalize slashes
        if '#' in src:
            src = src.split('#')[0]
        return os.path.normpath(src).replace('\\', '/').lower()
    
    def extract_chapter_content(self, chapter_info):
        """Extract and process content from all items in a chapter"""
        content_dir = self.metadata['content_dir']
        
        if not chapter_info.get('item_paths'):
            # Legacy support for single-file chapters
            src = chapter_info['src']
            full_path = os.path.normpath(os.path.join(content_dir, src))
            
            if not os.path.exists(full_path):
                print(f"Warning: Chapter file not found: {full_path}")
                return None, {}
            
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract images
            images = {}
            for img in soup.find_all('img'):
                src = img.get('src')
                if src:
                    # Generate a unique filename using UUID instead of MD5 hash
                    unique_id = str(uuid.uuid4())
                    new_filename = f"{unique_id}.jpg"
                    
                    # Update the src in the HTML
                    img['src'] = f"images/{new_filename}"
                    img['alt'] = new_filename
                    
                    # Record the image mapping
                    images[new_filename] = os.path.normpath(os.path.join(os.path.dirname(full_path), src))
            
            # Extract the body content - get everything inside the body tag
            body = soup.find('body')
            if body:
                html_content = ''.join(str(tag) for tag in body.contents if tag)
            else:
                html_content = str(soup)
            
            return html_content, images
        
        # For multi-file chapters, concatenate all content
        combined_html = ""
        all_images = {}
        
        for filepath in chapter_info['item_paths']:
            if not os.path.exists(filepath):
                print(f"Warning: Chapter file not found: {filepath}")
                continue
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                soup = BeautifulSoup(content, 'html.parser')
                
                # Extract images
                for img in soup.find_all('img'):
                    src = img.get('src')
                    if src:
                        # Generate a unique filename using UUID instead of MD5 hash
                        unique_id = str(uuid.uuid4())
                        new_filename = f"{unique_id}.jpg"
                        
                        # Update the src in the HTML
                        img['src'] = f"images/{new_filename}"
                        img['alt'] = new_filename
                        
                        # Record the image mapping
                        all_images[new_filename] = os.path.normpath(os.path.join(os.path.dirname(filepath), src))
                
                # Extract the body content
                body = soup.find('body')
                if body:
                    # Add a divider between files for clarity
                    if combined_html:
                        combined_html += "<hr/>"
                    
                    # Add content
                    file_content = ''.join(str(tag) for tag in body.contents if tag)
                    combined_html += file_content
            except Exception as e:
                print(f"Error processing file {filepath}: {e}")
        
        return combined_html, all_images
    
    def extract_synopsis_from_prologue(self):
        """Extract synopsis from prologue or first chapter if available"""
        if not self.metadata or not self.metadata.get('toc_path') or not os.path.exists(self.metadata['toc_path']):
            return None
        
        try:
            tree = ET.parse(self.metadata['toc_path'])
            root = tree.getroot()
            
            # Look for prologue or first chapter
            first_chapter = None
            for nav_point in root.findall('.//{http://www.daisy.org/z3986/2005/ncx/}navPoint'):
                label = nav_point.find('.//{http://www.daisy.org/z3986/2005/ncx/}navLabel/{http://www.daisy.org/z3986/2005/ncx/}text')
                content = nav_point.find('.//{http://www.daisy.org/z3986/2005/ncx/}content')
                
                if label is not None and content is not None:
                    title = label.text if label.text else ""
                    src = content.get('src')
                    
                    # Skip non-content entries
                    skip_keywords = ['toc', 'cover', 'copyright', 'about', 'color illustrations']
                    if any(keyword.lower() in title.lower() for keyword in skip_keywords):
                        continue
                    
                    first_chapter = {
                        'title': title,
                        'src': src
                    }
                    
                    # If we find a prologue, use that
                    if 'prologue' in title.lower():
                        break
                    
                    # Otherwise use the first chapter we find
                    if not first_chapter:
                        first_chapter = {
                            'title': title,
                            'src': src
                        }
            
            if first_chapter:
                # Extract content from the chapter
                html_content, _ = self.extract_chapter_content(first_chapter)
                if html_content:
                    # Clean up and limit the content
                    soup = BeautifulSoup(html_content, 'html.parser')
                    paragraphs = soup.find_all('p')
                    
                    # Use first few paragraphs (up to 3) as synopsis
                    synopsis_paragraphs = []
                    for i, p in enumerate(paragraphs):
                        if i >= 3:  # Limit to first 3 paragraphs
                            break
                        if p.text.strip():
                            synopsis_paragraphs.append(f"<p>{p.text.strip()}</p>")
                    
                    if synopsis_paragraphs:
                        return ''.join(synopsis_paragraphs)
        
        except Exception as e:
            print(f"Error extracting synopsis: {e}")
        
        return None
    
    def cleanup(self):
        """Clean up temporary files"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
