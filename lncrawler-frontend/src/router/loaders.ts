import { redirect, type LoaderFunctionArgs } from 'react-router-dom';
import { novelService } from '@services/api';
import { chatService } from '@services/chat.service';
import { readingListService } from '@services/readinglist.service';
import { getInitialContentLanguages, getInitialLanguageFilterEnabled } from '@context/LanguageContext';
import { getNovelSourcePath } from '@utils/Misc';
import type { Novel, NovelFromSource, Chapter } from '@models/novels_types';
import type { Review } from '@services/review.service';
import type { ChatPageResponse } from '@models/chat_types';
import type { ReadingList, ReadingListResponse } from '@models/readinglist_types';

// Shared with ChatPage so the loader's first page matches loadMore's pages.
export const CHAT_PAGE_SIZE = 100;

export interface HomeData {
  top_novels: Novel[];
  trending_novels: Novel[];
  top_rated_novels: Novel[];
  recently_added: Novel[];
  recently_updated: NovelFromSource[];
  recent_reviews: Review[];
  recommended_novels: Novel[];
  novels_you_added: Novel[];
}

export type HomeLoaderData = { ok: true; data: HomeData } | { ok: false };

// Home is the cold-load path: this runs at module eval, before the i18n gate.
export const homeLoader = async (): Promise<HomeLoaderData> => {
  const languages = getInitialLanguageFilterEnabled() ? getInitialContentLanguages() : [];
  try {
    const data = (await novelService.getHomePageData(languages)) as HomeData;
    return { ok: true, data };
  } catch {
    return { ok: false };
  }
};

export type NovelRedirectLoaderData = { ok: false };

export const novelRedirectLoader = async ({ params }: LoaderFunctionArgs) => {
  const novelSlug = params.novelSlug;
  if (!novelSlug) return redirect('/');
  try {
    const novel = await novelService.getNovelDetail(novelSlug);
    const target = getNovelSourcePath(novel);
    if (!target) return { ok: false } satisfies NovelRedirectLoaderData;
    return redirect(target);
  } catch {
    return { ok: false } satisfies NovelRedirectLoaderData;
  }
};

export type ChatLoaderData = { ok: true; data: ChatPageResponse } | { ok: false };

export const chatLoader = async (): Promise<ChatLoaderData> => {
  try {
    return { ok: true, data: await chatService.listChat(1, CHAT_PAGE_SIZE) };
  } catch {
    return { ok: false };
  }
};

export type ReadingListsLoaderData = { ok: true; data: ReadingListResponse } | { ok: false };

export const readingListsLoader = async ({ request }: LoaderFunctionArgs): Promise<ReadingListsLoaderData> => {
  const url = new URL(request.url);
  const page = Number(url.searchParams.get('page')) || 1;
  const q = url.searchParams.get('q') || '';
  try {
    return { ok: true, data: await readingListService.getAllReadingLists(page, 20, q) };
  } catch {
    return { ok: false };
  }
};

export type ReadingListDetailLoaderData = { ok: true; data: ReadingList } | { ok: false };

export const readingListDetailLoader = async ({ params }: LoaderFunctionArgs): Promise<ReadingListDetailLoaderData> => {
  const listId = params.listId;
  if (!listId) return { ok: false };
  try {
    return { ok: true, data: await readingListService.getReadingListDetail(listId) };
  } catch {
    return { ok: false };
  }
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

export const chapterListLoader = async ({ params, request }: LoaderFunctionArgs): Promise<ChapterListLoaderData> => {
  const { novelSlug, sourceSlug } = params;
  if (!novelSlug || !sourceSlug) return { ok: false };
  const url = new URL(request.url);
  const page = Number(url.searchParams.get('page')) || 1;
  const pageSize = Number(url.searchParams.get('page_size')) || 100;
  const q = url.searchParams.get('q') || '';
  try {
    const data = (await novelService.getNovelChapters(novelSlug, sourceSlug, page, pageSize, q)) as ChapterListData;
    return { ok: true, data };
  } catch {
    return { ok: false };
  }
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

export const galleryLoader = async ({ params, request }: LoaderFunctionArgs): Promise<GalleryLoaderData> => {
  const { novelSlug, sourceSlug } = params;
  if (!novelSlug || !sourceSlug) return { ok: false };
  const url = new URL(request.url);
  const page = Number(url.searchParams.get('page')) || 1;
  try {
    return { ok: true, data: (await novelService.getSourceGallery(novelSlug, sourceSlug, page)) as GalleryData };
  } catch {
    return { ok: false };
  }
};

export interface SearchData {
  results: Novel[];
  count: number;
  total_pages: number;
  current_page: number;
  tags?: string[];
  authors?: string[];
  statuses?: string[];
  languages?: string[];
}

export type SearchLoaderData = { ok: true; data: SearchData } | { ok: false };

export const searchLoader = async ({ request }: LoaderFunctionArgs): Promise<SearchLoaderData> => {
  const sp = new URL(request.url).searchParams;
  const page = sp.get('page') ? parseInt(sp.get('page')!) : 1;
  const selectedLanguages = sp.getAll('language');
  try {
    const data = (await novelService.searchNovels({
      query: sp.get('query') || undefined,
      page,
      page_size: 24,
      tag: sp.getAll('tag'),
      exclude_tag: sp.getAll('exclude_tag'),
      author: sp.getAll('author'),
      status: sp.get('status') || undefined,
      languages: selectedLanguages.length > 0 ? selectedLanguages : undefined,
      min_rating: sp.get('min_rating') ? Number(sp.get('min_rating')) : undefined,
      sort_by: (sp.get('sort_by') as 'title' | 'rating' | 'date_added' | 'popularity' | 'trending' | 'last_updated') || 'title',
      sort_order: (sp.get('sort_order') as 'asc' | 'desc') || 'asc',
      adult: (sp.get('adult') as 'hide' | 'show' | 'only') || undefined,
    })) as SearchData;
    return { ok: true, data };
  } catch {
    return { ok: false };
  }
};
