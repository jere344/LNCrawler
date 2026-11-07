import { defaultSortOrder } from '@services/novel.service';

// Search filter params as the URL stores them. Shared by the search loader and the
// search page, so the request and the page's applied-filter key read the URL the same way.
export interface SearchFilters {
  tag: string[];
  exclude_tag: string[];
  author: string[];
  status: string;
  language: string[];
  min_rating: number | null;
  sort_by: string;
  sort_order: string;
  adult: string | null;
}

// `defaultLanguages` applies when the URL has no `language` key (first arrival).
export const parseSearchFilters = (sp: URLSearchParams, defaultLanguages: string[]): SearchFilters => {
  const sortBy = sp.get('sort_by') || 'popularity';
  return {
    tag: sp.getAll('tag'),
    exclude_tag: sp.getAll('exclude_tag'),
    author: sp.getAll('author'),
    status: sp.get('status') || '',
    // An empty `language=` marker means the user explicitly chose "all languages".
    language: sp.has('language') ? sp.getAll('language').filter(Boolean) : defaultLanguages,
    min_rating: sp.get('min_rating') ? Number(sp.get('min_rating')) : null,
    sort_by: sortBy,
    sort_order: sp.get('sort_order') || defaultSortOrder(sortBy),
    adult: sp.get('adult'),
  };
};
