import type { NovelFromSource, SourceView } from '@models/novels_types';

// Router state can hold a library card's preview of a source, or a summary of one, which have no
// authors. The page's full-only reads (tags, editors, counters, ...) are only safe on a full source,
// so authors is the marker: the detail fetch and the home cards' state both carry it.
export const isFullSource = (source: SourceView | null | undefined): source is NovelFromSource =>
  source != null && 'authors' in source;
