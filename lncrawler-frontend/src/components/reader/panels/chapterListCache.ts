import type { NovelChaptersResponse } from '@models/novels_types';

// A listing older than this is fetched again on the next open
export const CHAPTER_LIST_TTL_MS = 10 * 60 * 1000;

// One request for the chapter list: a page by number, or the page holding a chapter number (`around`)
export interface ChapterPageRequest {
  novelSlug: string;
  sourceSlug: string;
  page?: number;
  around?: number;
  search?: string;
}

export type ChapterPageFetcher = (request: ChapterPageRequest) => Promise<NovelChaptersResponse>;

// What is known about one source. A page keeps its own count, total pages and has_volumes.
interface Listing {
  fetchedAt: number;
  // Loaded pages, by search query and page number
  pages: Map<string, NovelChaptersResponse>;
  // The page that holds each chapter number asked for with `around` (unfiltered only)
  aroundPages: Map<number, number>;
  // Requests on their way, shared by every caller that asks for the same thing
  inflight: Map<string, Promise<NovelChaptersResponse>>;
}

export interface ChapterListCache {
  load: (request: ChapterPageRequest) => Promise<NovelChaptersResponse>;
}

const pageKey = (search: string, page: number) => JSON.stringify([search, page]);

// Creates a cache around `fetchPage`. Only successful responses are kept: a failed request is simply sent again.
export function createChapterListCache(
  fetchPage: ChapterPageFetcher,
  now: () => number = Date.now,
): ChapterListCache {
  const listings = new Map<string, Listing>();

  // The listing of a source; a missing or expired one is started afresh
  const listingFor = (novelSlug: string, sourceSlug: string): Listing => {
    const key = JSON.stringify([novelSlug, sourceSlug]);
    const existing = listings.get(key);
    if (existing && now() - existing.fetchedAt < CHAPTER_LIST_TTL_MS) return existing;
    const fresh: Listing = { fetchedAt: now(), pages: new Map(), aroundPages: new Map(), inflight: new Map() };
    listings.set(key, fresh);
    return fresh;
  };

  // Sends a request once for everyone who asks while it is in flight; `store` keeps a success
  const share = (
    listing: Listing,
    key: string,
    send: () => Promise<NovelChaptersResponse>,
    store: (data: NovelChaptersResponse) => void,
  ): Promise<NovelChaptersResponse> => {
    const pending = listing.inflight.get(key);
    if (pending) return pending;
    const request = send().then(
      (data) => {
        listing.inflight.delete(key);
        store(data);
        return data;
      },
      (error: unknown) => {
        listing.inflight.delete(key);
        throw error;
      },
    );
    listing.inflight.set(key, request);
    return request;
  };

  const loadPage = (listing: Listing, request: ChapterPageRequest, search: string, page: number) => {
    const key = pageKey(search, page);
    const loaded = listing.pages.get(key);
    if (loaded) return Promise.resolve(loaded);
    return share(
      listing,
      key,
      () => fetchPage({ novelSlug: request.novelSlug, sourceSlug: request.sourceSlug, page, search }),
      (data) => listing.pages.set(key, data),
    );
  };

  const loadAround = (listing: Listing, request: ChapterPageRequest, around: number) => {
    const known = listing.aroundPages.get(around);
    if (known !== undefined) return loadPage(listing, request, '', known);
    return share(
      listing,
      `around:${around}`,
      () => fetchPage({ novelSlug: request.novelSlug, sourceSlug: request.sourceSlug, around }),
      (data) => {
        listing.pages.set(pageKey('', data.current_page), data);
        listing.aroundPages.set(around, data.current_page);
      },
    );
  };

  return {
    load: (request) => {
      const listing = listingFor(request.novelSlug, request.sourceSlug);
      const search = request.search?.trim() ?? '';
      // The search ignores `around`, so only the unfiltered list can start at a chapter
      if (search === '' && request.page === undefined && request.around !== undefined) {
        return loadAround(listing, request, request.around);
      }
      return loadPage(listing, request, search, request.page ?? 1);
    },
  };
}
