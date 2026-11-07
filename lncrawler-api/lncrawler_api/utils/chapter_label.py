"""
How a chapter is named for readers: `Chapter.display_title` and every payload that
shows a chapter (API, epub, audiobooks, SEO, admin) go through this module.

- the source's own title when it already carries a chapter number, whether or
  not it is ours ("Chapter 12 - The Fool", "CH 5.5 - The Fool", "第十二章 愚者"),
- "12. The Fool" when it does not,
- "Chapter 12" (in the novel's language) when the title is empty.

The strings and patterns live in shared_constants.json. A labeler is built once per
language (regexes compiled once), so labelling a row costs no query and no compile.
"""
import re
import unicodedata
from functools import lru_cache

from ..languages import SHARED_CONSTANTS, normalize_language

CHAPTER_LABELS = _LABELS = SHARED_CONSTANTS['chapter_labels']
_TITLE_FORMAT = SHARED_CONSTANTS['chapter_title_format']
_NUMBER_PATTERNS = [re.compile(p, re.IGNORECASE) for p in SHARED_CONSTANTS['chapter_number_patterns']]


class ChapterLabeler:
    """Labels the chapters of one content language."""

    def __init__(self, language):
        code = normalize_language(language).split('-')[0]
        self._number_format = _LABELS.get(code, _LABELS['en'])

    def number_label(self, number):
        """"Chapter 12" in this language."""
        return self._number_format.replace('{number}', str(number))

    @staticmethod
    def has_number(title, number):
        """True when `title` starts with its own chapter number (any value: sources restart at 1
        per volume or use 5.5 for interludes) or contains ours as a standalone number."""
        # NFKC folds full-width digits (第１２章) to ASCII.
        text = unicodedata.normalize('NFKC', title)
        if any(p.search(text) for p in _NUMBER_PATTERNS):
            return True
        target = str(number)
        return any(run == target for run in re.findall(r'[0-9]+', text))

    def label(self, title, number):
        title = (title or '').strip()
        if not title:
            return self.number_label(number)
        if self.has_number(title, number):
            return title
        return _TITLE_FORMAT.replace('{number}', str(number)).replace('{title}', title)


@lru_cache(maxsize=None)
def get_labeler(language):
    return ChapterLabeler(language)


def format_chapter_label(title, number, language):
    return get_labeler(language).label(title, number)


def chapter_number_label(language, number):
    return get_labeler(language).number_label(number)


def has_chapter_number(title, number):
    return ChapterLabeler.has_number(title, number)
