import type { NovelFromSource } from '@models/novels_types';

export type SortKey = 'updated' | 'chapters' | 'rating' | 'name';
export type SortDir = 'asc' | 'desc';

export const SORT_KEYS: SortKey[] = ['updated', 'chapters', 'rating', 'name'];
export const DEFAULT_SORT: { key: SortKey; dir: SortDir } = { key: 'updated', dir: 'desc' };
// The direction a sort starts in; picking it again reverses it.
export const DEFAULT_SORT_DIR: Record<SortKey, SortDir> = {
  updated: 'desc',
  chapters: 'desc',
  rating: 'desc',
  name: 'asc',
};

export const ALL = 'all';

export interface SourceFilters {
  query: string;
  language: string;
  edition: string;
}

export const sourceChapterCount = (s: NovelFromSource): number => s.available_chapters_count ?? s.chapters_count ?? 0;
export const languageKey = (s: NovelFromSource): string => (s.language ?? '').toLowerCase();
export const editionKey = (s: NovelFromSource): string => (s.edition ?? '').trim().toLowerCase();

const cleanName = (name: string): string => name.replace(/^www\./i, '');

// The language filter starts on the current source's language, or on all of them when no other
// source shares it (so the list never opens empty).
export function defaultLanguage(others: NovelFromSource[], current: NovelFromSource | undefined): string {
  const language = current ? languageKey(current) : '';
  return language && others.some((s) => languageKey(s) === language) ? language : ALL;
}

export function matchesFilters(s: NovelFromSource, f: SourceFilters): boolean {
  if (f.language !== ALL && languageKey(s) !== f.language) return false;
  if (f.edition !== ALL && editionKey(s) !== f.edition) return false;
  const query = f.query.trim().toLowerCase();
  if (!query) return true;
  const haystack = [s.source_name, s.title, s.latest_available_chapter?.display_title ?? ''].join(' ').toLowerCase();
  return haystack.includes(query);
}

// How many sources each value of one facet would list, with the other filters (and the search) applied.
export function facetCounts(sources: NovelFromSource[], f: SourceFilters, facet: 'language' | 'edition'): Map<string, number> {
  const counts = new Map<string, number>();
  for (const s of sources) {
    if (!matchesFilters(s, { ...f, [facet]: ALL })) continue;
    const key = facet === 'language' ? languageKey(s) : editionKey(s);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

// `ratings` is the score each source had when the list loaded: sorting on it keeps a row in place
// while the reader votes on it.
export function sortSources(
  sources: NovelFromSource[],
  key: SortKey,
  dir: SortDir,
  ratings: Record<string, number>,
): NovelFromSource[] {
  const sign = dir === 'asc' ? 1 : -1;
  return [...sources].sort((a, b) => {
    let diff: number;
    if (key === 'updated') diff = Date.parse(a.last_chapter_update) - Date.parse(b.last_chapter_update);
    else if (key === 'chapters') diff = sourceChapterCount(a) - sourceChapterCount(b);
    else if (key === 'rating') diff = (ratings[a.source_slug] ?? a.vote_score) - (ratings[b.source_slug] ?? b.vote_score);
    else diff = cleanName(a.source_name).localeCompare(cleanName(b.source_name));
    return diff !== 0 ? diff * sign : sourceChapterCount(b) - sourceChapterCount(a);
  });
}
