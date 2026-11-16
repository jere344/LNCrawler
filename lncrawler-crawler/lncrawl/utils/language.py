"""Language guess from text, for multi-language sources with no per-novel language field.

Script check first (zh/ja/ko/th/ru), then stopword scoring for Latin-script
languages. Standard library only. Returns an ISO 639-1 code, or "" when unsure,
so the caller keeps its own default. Indonesian and Malay overlap heavily and
may be confused.
"""
import re

_SCRIPTS = (
    ("ja", re.compile(r"[\u3040-\u30ff]")),
    ("ko", re.compile(r"[\uac00-\ud7af]")),
    ("zh", re.compile(r"[\u3400-\u9fff]")),
    ("th", re.compile(r"[\u0e00-\u0e7f]")),
    ("ru", re.compile(r"[\u0400-\u04ff]")),
)
_STOPWORDS = {
    "en": "the and of to in is that it was he she you with for his her they not on but".split(),
    "id": "yang dan di ini itu dengan untuk tidak aku kamu dia nya bisa gak nggak sudah akan".split(),
    "ms": "yang dan di ini itu dengan untuk tidak saya awak kami boleh sangat hendak telah".split(),
    "tl": "ang ng sa na mga ay ako ka siya hindi para ito nang pero kung".split(),
    "vi": "và của là không có một những được trong cho này người với đã".split(),
    "de": "der die das und ist nicht ein ich sie er mit zu den von auf für".split(),
    "es": "el la los las de que y en un una es no se por con para su pero".split(),
    "fr": "le la les des et est un une que qui dans pour pas je il elle sur avec".split(),
    "it": "il lo gli le di che e un una è non per con sono ma della questo".split(),
}
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def guess_language(text: str) -> str:
    """ISO 639-1 code guessed from text, "" when there is not enough to tell."""
    text = (text or "").strip()
    if len(text) < 30:
        return ""
    for code, rx in _SCRIPTS:
        if len(rx.findall(text)) >= max(5, len(text) // 20):
            return code
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if len(words) < 8:
        return ""
    best, best_score = "", 0
    for code, stop in _STOPWORDS.items():
        stop = set(stop)
        score = sum(1 for w in words if w in stop)
        if score > best_score:
            best, best_score = code, score
    return best if best_score >= 3 else ""
