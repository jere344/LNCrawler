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
  // The stored page for a request, if it is loaded already; never sends a request
  peek: (request: ChapterPageRequest) => NovelChaptersResponse | undefined;
}

const pageKey = (search: string, page: number) => JSON.stringify([search, page]);
const sourceKey = (novelSlug: string, sourceSlug: string) => JSON.stringify([novelSlug, sourceSlug]);
const searchOf = (request: ChapterPageRequest) => request.search?.trim() ?? '';
// Only the unfiltered list can start at a chapter: the search ignores `around`
const aroundOf = (request: ChapterPageRequest) =>
  searchOf(request) === '' && request.page === undefined ? request.around : undefined;

// The page of the unfiltered list that holds a chapter number: from an earlier `around` answer, else from a loaded page
function findAroundPage(listing: Listing, around: number): number | undefined {
  const known = listing.aroundPages.get(around);
  if (known !== undefined) return known;
  for (const data of listing.pages.values()) {
    // A search result is stored under its own query, so only the unfiltered pages count
    const unfiltered = listing.pages.get(pageKey('', data.current_page)) === data;
    if (unfiltered && data.chapters.some((chapter) => chapter.chapter_id === around)) return data.current_page;
  }
  return undefined;
}

// Creates a cache around `fetchPage`. Only successful responses are kept: a failed request is simply sent again.
export function createChapterListCache(
  fetchPage: ChapterPageFetcher,
  now: () => number = Date.now,
): ChapterListCache {
  const listings = new Map<string, Listing>();

  // The listing of a source while it is fresh; a missing or expired one is not returned, and an expired one is dropped
  const freshListing = (novelSlug: string, sourceSlug: string): Listing | undefined => {
    const key = sourceKey(novelSlug, sourceSlug);
    const existing = listings.get(key);
    if (!existing) return undefined;
    if (now() - existing.fetchedAt < CHAPTER_LIST_TTL_MS) return existing;
    listings.delete(key);
    return undefined;
  };

  // Forgets a listing whose answers no longer match the server: the next load fetches it again
  const dropListing = (novelSlug: string, sourceSlug: string, listing: Listing) => {
    const key = sourceKey(novelSlug, sourceSlug);
    if (listings.get(key) === listing) listings.delete(key);
  };

  // The fresh listing of a source, or a new one in place of a missing or expired one
  const listingFor = (novelSlug: string, sourceSlug: string): Listing => {
    const existing = freshListing(novelSlug, sourceSlug);
    if (existing) return existing;
    const fresh: Listing = { fetchedAt: now(), pages: new Map(), aroundPages: new Map(), inflight: new Map() };
    listings.set(sourceKey(novelSlug, sourceSlug), fresh);
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
      // The server answers a page past the end with its last page: the list has shrunk, so it is not kept
      (data) => {
        if (data.current_page === page) listing.pages.set(key, data);
        else dropListing(request.novelSlug, request.sourceSlug, listing);
      },
    );
  };

  const loadAround = (listing: Listing, request: ChapterPageRequest, around: number) => {
    const known = findAroundPage(listing, around);
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
      const around = aroundOf(request);
      if (around !== undefined) return loadAround(listing, request, around);
      return loadPage(listing, request, searchOf(request), request.page ?? 1);
    },
    peek: (request) => {
      const listing = freshListing(request.novelSlug, request.sourceSlug);
      if (!listing) return undefined;
      const around = aroundOf(request);
      if (around === undefined) return listing.pages.get(pageKey(searchOf(request), request.page ?? 1));
      const page = findAroundPage(listing, around);
      return page === undefined ? undefined : listing.pages.get(pageKey('', page));
    },
  };
}
