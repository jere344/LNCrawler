"""
Single registry of the languages this project understands.

Content languages are stored on NovelFromSource.language using these ISO 639-1
codes. The same list doubles as the set of selectable interface languages, so
the backend validates incoming preference values against it.
"""

SUPPORTED_LANGUAGES = [
    'en',
    'fr',
    'es',
    'de',
    'it',
    'ja',
    'ko',
    'zh',
    'pt',
    'ru',
    'ar',
    'hi',
    'th',
    'vi',
    'id',
    'tr',
    'pl',
    'nl',
    'sv',
    'da',
]

SUPPORTED_LANGUAGES_SET = set(SUPPORTED_LANGUAGES)

# Arabic renders right-to-left; every other supported language is LTR.
RTL_LANGUAGES = {'ar'}


def normalize_language(code):
    """Lower-case and strip a language code, returning '' for falsy input."""
    return (code or '').strip().lower()


def is_supported_language(code):
    return normalize_language(code) in SUPPORTED_LANGUAGES_SET


def parse_languages(raw_values):
    """
    Normalize an iterable of raw language values into a de-duplicated list of
    supported codes, preserving first-seen order.
    """
    if raw_values is None:
        return []
    if isinstance(raw_values, str):
        raw_values = [raw_values]
    result = []
    for value in raw_values:
        for part in str(value).split(','):
            code = normalize_language(part)
            if code in SUPPORTED_LANGUAGES_SET and code not in result:
                result.append(code)
    return result
