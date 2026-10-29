import type { LoaderFunctionArgs } from 'react-router-dom';
import { novelService } from '@services/api';
import { defaultSortOrder } from '@services/novel.service';
import { chatService } from '@services/chat.service';
import { readingListService } from '@services/readinglist.service';
import { getInitialContentLanguages, getInitialLanguageFilterEnabled } from '@context/LanguageContext';
import { getNovelSourcePath } from '@utils/Misc';
import type { Novel, NovelFromSource, Chapter } from '@models/novels_types';
import type { Review } from '@services/review.service';
import type { ChatPageResponse } from '@models/chat_types';
import type { HomeAudiobooks } from '@models/audiobook_types';
import type { ReadingList, ReadingListResponse } from '@models/readinglist_types';
import type { NovelSort } from '../generated/sharedConstants';

// Shared with ChatPage so the loader's first page matches loadMore's pages.
export const CHAT_PAGE_SIZE = 100;

// A route loader hands its request back un-awaited so the navigation transition
// isn't blocked: the component suspends on the promise (React 19 `use`) and
// shows its Suspense fallback until it resolves. `settle` folds request errors
// into the `{ ok: false }` shape the components already handle.
export interface AsyncData<T> {
  data: Promise<T>;
}

const settle = <T>(promise: Promise<T>): Promise<{ ok: true; data: T } | { ok: false }> =>
  promise.then((data) => ({ ok: true, data })).catch(() => ({ ok: false }));

// Back/forward shows a page as it was left instead of refetching it: the last
// successful result of each loader is kept by URL, and a history navigation
// (popstate) to that URL reuses it. The promise is marked fulfilled so `use`
// reads it without suspending: the page renders at full height in the same
// commit, which is what lets the scroll restore land.
const HISTORY_CACHE_SIZE = 20;
const historyCache = new Map<string, unknown>();
let poppedUrl: string | null = null;

// Registered before createBrowserRouter's own listener (router.tsx imports this
// module first), so it is set by the time the router calls the loaders.
window.addEventListener('popstate', () => {
  const url = new URL(window.location.href);
  url.hash = '';
  poppedUrl = url.href;
  // Only for the loaders of this navigation: one that runs none (a hash-only
  // change) must not leave it set for a later link to the same URL.
  setTimeout(() => { poppedUrl = null; });
});

// The cached results carry the account's bookmarks, ratings and recommendations.
export const clearHistoryCache = () => historyCache.clear();

const fulfilled = <T>(value: T): Promise<T> =>
  Object.assign(Promise.resolve(value), { status: 'fulfilled', value });

const reuseOnHistory = <T extends { ok: boolean }>(
  request: Request,
  key: string,
  load: () => Promise<T>,
): Promise<T> => {
  const fromHistory = request.url === poppedUrl;
  poppedUrl = null;
  if (fromHistory && historyCache.has(key)) return fulfilled(historyCache.get(key) as T);
  const promise = load();
  promise.then((result) => {
    if (!result.ok) return;
    historyCache.delete(key);
    historyCache.set(key, result);
    if (historyCache.size > HISTORY_CACHE_SIZE) historyCache.delete(historyCache.keys().next().value!);
  });
  return promise;
};

export interface HomeData {
  top_novels: Novel[];
  trending_novels: Novel[];
  top_rated_novels: Novel[];
  recently_added: Novel[];
  recently_updated: NovelFromSource[];
  recent_reviews: Review[];
  recommended_novels: Novel[];
  audiobooks?: HomeAudiobooks;
}

export type HomeLoaderData = { ok: true; data: HomeData } | { ok: false };

// Still fires at module eval, before the i18n gate (the cold-load prefetch),
// because createBrowserRouter initializes synchronously.
export const homeLoader = ({ request }: LoaderFunctionArgs): AsyncData<HomeLoaderData> => {
  const languages = getInitialLanguageFilterEnabled() ? getInitialContentLanguages() : [];
  return {
    data: reuseOnHistory(request, `${request.url}|${languages.join(',')}`, () =>
      settle<HomeData>(novelService.getHomePageData(languages)),
    ),
  };
};

export type NovelRedirectLoaderData = { ok: true; target: string } | { ok: false };

// Resolves to the novel's preferred source page. Un-awaited like the other
// loaders, so the redirect page's skeleton shows while the lookup runs instead
// of the previous page staying on screen.
export const novelRedirectLoader = ({ params }: LoaderFunctionArgs): AsyncData<NovelRedirectLoaderData> => {
  const novelSlug = params.novelSlug;
  if (!novelSlug) return { data: Promise.resolve<NovelRedirectLoaderData>({ ok: false }) };
  const resolve = async (): Promise<NovelRedirectLoaderData> => {
    try {
      const novel = await novelService.getNovelDetail(novelSlug);
      const target = getNovelSourcePath(novel);
      return target ? { ok: true, target } : { ok: false };
    } catch {
      return { ok: false };
    }
  };
  return { data: resolve() };
};

export type ChatLoaderData = { ok: true; data: ChatPageResponse } | { ok: false };

export const chatLoader = (): AsyncData<ChatLoaderData> => ({
  data: settle(chatService.listChat(1, CHAT_PAGE_SIZE)),
});

export type ReadingListsLoaderData = { ok: true; data: ReadingListResponse } | { ok: false };

export const readingListsLoader = ({ request }: LoaderFunctionArgs): AsyncData<ReadingListsLoaderData> => {
  const url = new URL(request.url);
  const page = Number(url.searchParams.get('page')) || 1;
  const q = url.searchParams.get('q') || '';
  return { data: settle(readingListService.getAllReadingLists(page, 20, q)) };
};

export type ReadingListDetailLoaderData = { ok: true; data: ReadingList } | { ok: false };

export const readingListDetailLoader = ({ params }: LoaderFunctionArgs): AsyncData<ReadingListDetailLoaderData> => {
  const listId = params.listId;
  if (!listId) return { data: Promise.resolve<ReadingListDetailLoaderData>({ ok: false }) };
  return { data: settle(readingListService.getReadingListDetail(listId)) };
};

export interface ChapterListData {
  chapters: Chapter[];
  count: number;
  total_pages: number;
  current_page: number;
  novel_title: string;
  source_name: string;
  is_dmca: boolean;
  source_overview_image_url?: string | null;
}

export type ChapterListLoaderData = { ok: true; data: ChapterListData } | { ok: false };

export const chapterListLoader = ({ params, request }: LoaderFunctionArgs): AsyncData<ChapterListLoaderData> => {
  const { novelSlug, sourceSlug } = params;
  if (!novelSlug || !sourceSlug) return { data: Promise.resolve<ChapterListLoaderData>({ ok: false }) };
  const url = new URL(request.url);
  const page = Number(url.searchParams.get('page')) || 1;
  const pageSize = Number(url.searchParams.get('page_size')) || 100;
  const q = url.searchParams.get('q') || '';
  return {
    data: reuseOnHistory(request, request.url, () =>
      settle<ChapterListData>(novelService.getNovelChapters(novelSlug, sourceSlug, page, pageSize, q)),
    ),
  };
};

export interface GalleryImage {
  chapter_id: number;
  chapter_title: string;
  image_url: string;
  image_name: string;
}

export interface GalleryData {
  novel_id: string;
  novel_title: string;
  novel_slug: string;
  source_id: string;
  source_name: string;
  source_slug: string;
  count: number;
  total_pages: number;
  current_page: number;
  images: GalleryImage[];
}

export type GalleryLoaderData = { ok: true; data: GalleryData } | { ok: false };

export const galleryLoader = ({ params, request }: LoaderFunctionArgs): AsyncData<GalleryLoaderData> => {
  const { novelSlug, sourceSlug } = params;
  if (!novelSlug || !sourceSlug) return { data: Promise.resolve<GalleryLoaderData>({ ok: false }) };
  const url = new URL(request.url);
  const page = Number(url.searchParams.get('page')) || 1;
  return {
    data: reuseOnHistory(request, request.url, () =>
      settle<GalleryData>(novelService.getSourceGallery(novelSlug, sourceSlug, page)),
    ),
  };
};

export interface SearchData {
  results: Novel[];
  count: number;
  total_pages: number;
  current_page: number;
  // Adult matches left out by the "hide" filter (0 for other modes).
  hidden_adult?: number;
  tags?: string[];
  authors?: string[];
  statuses?: string[];
  languages?: string[];
}

export type SearchLoaderData = { ok: true; data: SearchData } | { ok: false };

export const searchLoader = ({ request }: LoaderFunctionArgs): AsyncData<SearchLoaderData> => {
  const sp = new URL(request.url).searchParams;
  const page = sp.get('page') ? parseInt(sp.get('page')!) : 1;
  // An empty `language=` marker means the user explicitly chose "all languages";
  // no language key at all means first arrival, so the stored defaults apply.
  const selectedLanguages = sp.has('language')
    ? sp.getAll('language').filter(Boolean)
    : (getInitialLanguageFilterEnabled() ? getInitialContentLanguages() : []);
  const sortBy = (sp.get('sort_by') as NovelSort) || 'popularity';
  return {
    data: reuseOnHistory(request, `${request.url}|${selectedLanguages.join(',')}`, () =>
      settle<SearchData>(novelService.searchNovels({
        query: sp.get('query') || undefined,
        page,
        page_size: 24,
        tag: sp.getAll('tag'),
        exclude_tag: sp.getAll('exclude_tag'),
        author: sp.getAll('author'),
        status: sp.get('status') || undefined,
        languages: selectedLanguages.length > 0 ? selectedLanguages : undefined,
        min_rating: sp.get('min_rating') ? Number(sp.get('min_rating')) : undefined,
        sort_by: sortBy,
        sort_order: (sp.get('sort_order') as 'asc' | 'desc') || defaultSortOrder(sortBy),
        adult: (sp.get('adult') as 'hide' | 'show' | 'only') || undefined,
      })),
    ),
  };
};
