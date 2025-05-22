"""
Expected output architecture: :


OUTPUT_PATH/[novel_name]/LNCrawler/
    - meta.json
    - cover.jpg    
    - json/
        - [chapter_number:5d].json
    - images/
        - [image_name].jpg

meta.json expected output :
OUTPUT_PATH/A Returner'S Magic Should Be Special/LNCrawler/meta.json
{
    "novel": {
        "url": "https://readlightnovel.app/a-returners-magic-should-be-special",
        "title": "A Returner'S Magic Should Be Special",
        "authors": [
            "YunSoo",
        ],
        "cover_url": "https://readln.org/uploads/posters/1549698496.jpg",
        "chapters": [
            {
                "id": 1,
                "url": "https://readln.org/a-returners-magic-should-be-special/chapter-1",
                "title": "Chapter 1 - Prologue",
                "volume": 1,
                "volume_title": "Volume 1",
                "body": null,
                "images": {},
                "success": true
            },
            ...
            {
                "id": 49,
                "url": "https://readln.org/a-returners-magic-should-be-special/chapter-49",
                "title": "Chapter 49 - hello world",
                "volume": 1,
                "volume_title": "Volume 1",
                "body": null,
                "images": {
                    "8a2878683cd9f16f373886761c8018d0.jpg": null,
                },
                "success": true
            },
           ...
        ],
        "volumes": [
            {
                "id": 1,
                "title": "Volume 1",
                "start_chapter": 1,
                "final_chapter": 50,
                "chapter_count": 50
            },
            {
                "id": 2,
                "title": "Volume 2",
                "start_chapter": 51,
                "final_chapter": 100,
                "chapter_count": 50
            },
            ...
        ],
        "is_rtl": false,
        "synopsis": "<p> Lorem ipsum dolor sit amet, consectetur adipiscing elit. </p><p> Donec a diam lectus. Sed sit amet ipsum mauris. Maecenas </p>",
        "language": "en",
        "novel_tags": ["Action", "Adventure", "Fantasy", "Harem", "Romance"],
        "has_manga": null,
        "has_mtl": null,
        "language_code": [],
        "source": null,
        "editors": [],
        "translators": [],
        "status": "Unknown",
        "original_publisher": null,
        "english_publisher": null,
        "novelupdates_url": null
    },
}

expected chapter json output :
OUTPUT_PATH/A Returner'S Magic Should Be Special/LNCrawler/json/49.json
{
    "id": 49,
    "url": "https://readln.org/a-returners-magic-should-be-special/chapter-49",
    "title": "Ch 49",
    "volume": 1,
    "volume_title": "Volume 1",
    "body": "<h1>Chapter 49 - hello world/h1><p>Romantica threw her quill pen down at the table. Ink splattered all over, drenching various sheets of paper with the black liquid.</p><img alt=\"8a2878683cd9f16f373886761c8018d0.jpg\" src=\"images/8a2878683cd9f16f373886761c8018d0.jpg\"/><p>She hit her head on the floor and a sharp pain rattled her skull. </p>",
    "images": {
        "8a2878683cd9f16f373886761c8018d0.jpg": null,
    },
    "success": true
}

expected image output :
OUTPUT_PATH/A Returner'S Magic Should Be Special/LNCrawler/images/8a2878683cd9f16f373886761c8018d0.jpg -> the image file
"""



import os
from multi_epub_parser import MultiEpubParser

# EPUB namespaces
NAMESPACES = {
    'opf': 'http://www.idpf.org/2007/opf',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'ncx': 'http://www.daisy.org/z3986/2005/ncx/'
}


if __name__ == "__main__":
    
    library_path = os.path.join("D:\\", "ebooks", "test")
    for dir in os.listdir(library_path):
        input_dir = os.path.join(library_path, dir)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(current_dir, "output")
        
        # Create output directory
        os.makedirs(output_path, exist_ok=True)
        
        # Process all EPUBs in the directory
        parser = MultiEpubParser(input_dir, output_path)
        parser.process()