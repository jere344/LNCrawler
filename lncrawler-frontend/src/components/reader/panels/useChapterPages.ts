import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { Chapter, NovelChaptersResponse } from '@models/novels_types';
import type { ChapterPageRequest } from './chapterListCache';
import { CHAPTER_PAGE_SIZE, chapterIndex, chapterListCache } from './chapterList';

// The list as loaded so far; `query` is the search it answers ('' for the whole list)
interface ChapterPages {
  query: string;
  count: number;
  hasVolumes: boolean;
  pages: Map<number, NovelChaptersResponse>;
}

interface ChapterPagesOptions {
  novelSlug: string;
  sourceSlug: string;
  currentChapterId: number;
  query: string;
}

// The first page: page 1 of a search, or the page holding the chapter being read
const firstRequest = (
  { novelSlug, sourceSlug, currentChapterId }: Omit<ChapterPagesOptions, 'query'>,
  search: string,
): ChapterPageRequest =>
  search ? { novelSlug, sourceSlug, page: 1, search } : { novelSlug, sourceSlug, around: currentChapterId };

const viewOf = (query: string, data: NovelChaptersResponse): ChapterPages => ({
  query,
  count: data.count,
  hasVolumes: data.has_volumes,
  pages: new Map([[data.current_page, data]]),
});

// The view with one more page; the same object when that page is in it already
const withPage = (view: ChapterPages, data: NovelChaptersResponse): ChapterPages =>
  view.pages.get(data.current_page) === data
    ? view
    : { ...view, pages: new Map(view.pages).set(data.current_page, data) };

// The chapter list page by page: the first page on open or on a search, then the pages the rows in view need
export function useChapterPages({ novelSlug, sourceSlug, currentChapterId, query }: ChapterPagesOptions) {
  // The latest list loaded: it may answer an older query while the new one loads
  const [view, setView] = useState<ChapterPages | null>(() => {
    const cached = chapterListCache.peek(firstRequest({ novelSlug, sourceSlug, currentChapterId }, ''));
    return cached ? viewOf('', cached) : null;
  });
  const [failed, setFailed] = useState(false);
  // Bumped by every first-page load: a first page from an older load is dropped
  const session = useRef(0);
  // The query asked for last: a failure for an older one is not shown
  const latestQuery = useRef(query);
  const viewQuery = view?.query;

  // The first page of `search`: from the cache when it is there, else fetched
  const loadFirst = useCallback(async (search: string) => {
    const token = ++session.current;
    const request = firstRequest({ novelSlug, sourceSlug, currentChapterId }, search);
    setFailed(false);
    const cached = chapterListCache.peek(request);
    if (cached) {
      setView(viewOf(search, cached));
      return;
    }
    try {
      const data = await chapterListCache.load(request);
      if (token === session.current) {
        setView(viewOf(search, data));
        setFailed(false);
      }
    } catch {
      if (token === session.current) setFailed(true);
    }
  }, [novelSlug, sourceSlug, currentChapterId]);

  // A query the view does not answer yet is loaded; the view on screen stays until then.
  // Before paint, so a cached view replaces the old rows without showing them for a frame.
  useLayoutEffect(() => {
    latestQuery.current = query;
    if (viewQuery === query) {
      // Drops a first page still on its way for an older query
      session.current++;
      setFailed(false);
      return;
    }
    void loadFirst(query);
  }, [query, viewQuery, loadFirst]);

  // Sends the failed request again: the first page, or the pages the panel asks for once `failed` clears
  const retry = () => {
    if (viewQuery === query) setFailed(false);
    else void loadFirst(query);
  };

  // Loads pages first..last of the list shown; the cache answers the ones it has
  const loadPages = useCallback((first: number, last: number) => {
    if (viewQuery === undefined) return;
    const search = viewQuery;
    for (let page = first; page <= last; page++) {
      chapterListCache.load({ novelSlug, sourceSlug, page, search })
        .then((data) => {
          // The list shrank on the server: the view is reloaded from its first page, unless the query has moved on
          if (data.current_page !== page) {
            if (latestQuery.current === search) void loadFirst(search);
            return;
          }
          // A page for a query the view no longer shows is dropped
          setView((previous) => (previous?.query === search ? withPage(previous, data) : previous));
        })
        .catch(() => {
          if (latestQuery.current === search) setFailed(true);
        });
    }
  }, [novelSlug, sourceSlug, viewQuery, loadFirst]);

  // The chapter at a row of the unfiltered or search list, when its page is loaded
  const chapterAt = (index: number): Chapter | undefined =>
    view?.pages.get(Math.floor(index / CHAPTER_PAGE_SIZE) + 1)?.chapters[index % CHAPTER_PAGE_SIZE];

  // Where the chapter being read sits in the whole list, once its page is loaded
  const currentIndex = useMemo(() => {
    if (view?.query !== '') return null;
    for (const page of view.pages.values()) {
      const index = chapterIndex(page, currentChapterId);
      if (index !== null) return index;
    }
    return null;
  }, [view, currentChapterId]);

  return { view, failed, retry, chapterAt, loadPages, currentIndex };
}
