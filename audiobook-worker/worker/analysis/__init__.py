"""Worker-side analysis of a part: cast detection, speaker attribution, and the sentences and cast rows built from them."""

from worker.analysis.attribution import ChunkResult, attribute_chapter, attribute_chunk, chunk_pieces
from worker.analysis.cast import CastEntry, detect_cast, reply_schema
from worker.analysis.run import DEFAULT_NARRATOR_STYLE, NARRATOR, PALETTE, PartAnalysis, analyse_part

__all__ = [
    "CastEntry",
    "ChunkResult",
    "DEFAULT_NARRATOR_STYLE",
    "NARRATOR",
    "PALETTE",
    "PartAnalysis",
    "analyse_part",
    "attribute_chapter",
    "attribute_chunk",
    "chunk_pieces",
    "detect_cast",
    "reply_schema",
]
