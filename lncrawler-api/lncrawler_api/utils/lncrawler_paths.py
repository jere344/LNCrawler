from django.conf import settings
import os
import shutil
import unicodedata
import re

from .slug import slugify

# A trailing " [..]" on a source folder name marks a second source of the same
# site inside one novel, e.g. "foo [ln]" or "foo [2]".
_SOURCE_SUFFIX_RE = re.compile(r"\s+\[[^\[\]]*\]$")

# Longest edition slug kept in a "<site> [<slug>]" folder name.
EDITION_SLUG_MAX_BYTES = 60

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


def truncate_component(text: str, max_bytes: int = 180) -> str:
    """Bound a single path component so long names cannot exceed the fs limit."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    # Cut on a byte boundary without splitting a multibyte character.
    cut = encoded[:max_bytes].decode("utf-8", "ignore")
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.strip() or text[: max_bytes // 4]


def get_novel_output_path(source, novel) -> str:
    """
    Get the output path for a novel based on its source and name.
    The path format is BASE / NOVEL / SOURCE
    """
    # settings.py LNCRAWL_OUTPUT_PATH
    BASE_DIR = settings.LNCRAWL_OUTPUT_PATH

    # Normalize the source and novel names
    source = truncate_component(sanitize(source).lower())
    novel = truncate_component(sanitize(novel).lower())
    
    # Default names if empty after sanitization
    if not source:
        source = "unknown_source"
    if not novel:
        novel = "unknown_novel"
        
    # Apply novel naming rules
    novel = novel_naming_rules(novel)
    
    novel_dir = os.path.join(BASE_DIR, novel)
    source_dir = os.path.join(novel_dir, source)
    return source_dir


def move_and_merge_directory(source_dir: str, target_dir: str) -> None:
    """
    Move the contents of ``source_dir`` into ``target_dir``, overwriting
    same-named files and recursively merging subdirectories. ``source_dir`` is
    removed once empty.

    Used to consolidate a crawled/imported source folder into the canonical
    novel folder after a merge alias has been resolved. A plain ``shutil.move``
    would nest the source under the target when the latter already exists,
    which is not what we want here.
    """
    if os.path.abspath(source_dir) == os.path.abspath(target_dir):
        return

    os.makedirs(target_dir, exist_ok=True)
    for entry in os.listdir(source_dir):
        src = os.path.join(source_dir, entry)
        dst = os.path.join(target_dir, entry)
        try:
            if os.path.isdir(src):
                if os.path.exists(dst):
                    move_and_merge_directory(src, dst)
                else:
                    shutil.move(src, dst)
            else:
                if os.path.exists(dst):
                    os.remove(dst)
                shutil.move(src, dst)
        except FileNotFoundError:
            # The crawler keeps running while we consolidate and may create or
            # remove an entry (its .lncrawl.lock) mid-move. It is already gone,
            # so there is nothing left to move.
            continue

    try:
        os.rmdir(source_dir)
    except OSError:
        # Source still holds something we could not move; leave it in place
        # rather than risk deleting data.
        pass


def site_name_from_folder(basename: str) -> str:
    """Return the ExternalSource name for a source folder basename.

    ``"foo [ln]"`` and ``"foo [2]"`` name the site ``"foo"``; a plain folder is
    its own site name.
    """
    stripped = _SOURCE_SUFFIX_RE.sub("", basename or "")
    return stripped or (basename or "")


def free_source_folder(novel_abs_dir: str, site: str, edition: str, taken) -> str:
    """Return a folder name for another source of ``site`` inside a novel.

    The name is ``<site> [<edition slug>]`` when ``edition`` is set (e.g.
    ``site [official-translation]``), else ``<site> [2]``, ``[3]`` ... It is
    never a name in ``taken`` (the folder basenames of the novel's other rows)
    nor one already on disk.
    """
    # Capped so "<site> [<slug>]" stays far below the 255-byte name limit.
    edition_slug = truncate_component(slugify(edition or ""), EDITION_SLUG_MAX_BYTES).rstrip("-")
    if edition_slug:
        candidate = f"{site} [{edition_slug}]"
        if _folder_free(novel_abs_dir, candidate, taken):
            return candidate
    n = 2
    while True:
        candidate = f"{site} [{n}]"
        if _folder_free(novel_abs_dir, candidate, taken):
            return candidate
        n += 1


def _folder_free(novel_abs_dir: str, name: str, taken) -> bool:
    return name not in taken and not os.path.lexists(os.path.join(novel_abs_dir, name))


def remove_empty_directory(path: str) -> None:
    """Remove ``path`` if it exists and is empty. No-op otherwise."""
    try:
        os.rmdir(path)
    except OSError:
        pass


def rebase_path(path: str, old_prefix: str, new_prefix: str) -> str:
    """
    Replace the leading ``old_prefix`` component of a relative path with
    ``new_prefix``. Paths outside ``old_prefix`` are returned unchanged.
    """
    if not path or not old_prefix:
        return path
    if path == old_prefix:
        return new_prefix
    if path.startswith(old_prefix + os.sep):
        return new_prefix + path[len(old_prefix):]
    return path
