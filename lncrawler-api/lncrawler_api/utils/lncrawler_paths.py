from django.conf import settings
import os
import unicodedata
import re

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

    return text


def get_novel_output_path(source, novel) -> str:
    """
    Get the output path for a novel based on its source and name.
    The path format is BASE / NOVEL / SOURCE
    """
    # settings.py LNCRAWL_OUTPUT_PATH
    BASE_DIR = settings.LNCRAWL_OUTPUT_PATH
    # Create the base directory if it doesn't exist
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
    
    # Normalize the source and novel names
    source = sanitize(source)
    novel = sanitize(novel)
    
    # Default names if empty after sanitization
    if not source:
        source = "unknown_source"
    if not novel:
        novel = "unknown_novel"
        
    # Apply novel naming rules
    novel = novel_naming_rules(novel)
    
    # Create the novel directory if it doesn't exist
    novel_dir = os.path.join(BASE_DIR, novel)
    if not os.path.exists(novel_dir):
        os.makedirs(novel_dir)

    # Create the source directory if it doesn't exist
    source_dir = os.path.join(novel_dir, source)
    if not os.path.exists(source_dir):
        os.makedirs(source_dir)
    
    return source_dir
