import api from './api';
import { API_BASE_URL } from './config';
import { NovelChaptersResponse, SourceDetailResponse } from '@models/novels_types';
import type { NovelSort } from '../generated/sharedConstants';

// View count reads best most-viewed first; every other sort starts ascending.
export const defaultSortOrder = (sortBy: string): 'asc' | 'desc' => (sortBy === 'popularity' ? 'desc' : 'asc');

// Novel service functions updated for the new URL structure
export const novelService = {
  // Get novel details by slug
  getNovelDetail: async (novelSlug: string) => {
    const response = await api.get(`/novels/${novelSlug}/`);
    return response.data;
  },
  
  // Get source details by slug
  getSourceDetail: async (novelSlug: string, sourceSlug: string): Promise<SourceDetailResponse> => {
    const response = await api.get(`/novels/${novelSlug}/${sourceSlug}/`);
    return response.data;
  },
  
  // Get chapters by novel and source slugs with pagination. With `around`, the page holding that chapter number is returned instead of `page`.
  getNovelChapters: async (
    novelSlug: string,
    sourceSlug: string,
    page = 1,
    pageSize = 100,
    search = '',
    around?: number,
  ): Promise<NovelChaptersResponse> => {
    const params = around === undefined
      ? { page, page_size: pageSize, search }
      : { page_size: pageSize, search, around };
    const response = await api.get(`/novels/${novelSlug}/${sourceSlug}/chapters/`, { params });
    return response.data;
  },
  
  // Get chapter content by number
  getChapterContent: async (novelSlug: string, sourceSlug: string, chapterNumber: number) => {
    const response = await api.get(`/novels/${novelSlug}/${sourceSlug}/chapter/${chapterNumber}/`);
    return response.data;
  },

  voteSource : async (novelSlug: string, sourceSlug: string, voteType: 'up' | 'down') => {
    const response = await api.post(
      `/novels/${novelSlug}/${sourceSlug}/vote/`, 
      { vote_type: voteType }
    );
    return response.data;
  },

  // Rate a novel (1-5 stars)
  rateNovel: async (novelSlug: string, rating: number) => {
    const response = await api.post(`/novels/${novelSlug}/rate/`, { rating });
    return response.data;
  },

  searchNovels: async (params: {
    query?: string;
    page?: number;
    page_size?: number;
    tag?: string[];
    exclude_tag?: string[];
    author?: string[];
    status?: string;
    language?: string;
    languages?: string[];
    min_rating?: number;
    sort_by?: NovelSort;
    sort_order?: 'asc' | 'desc';
    adult?: 'hide' | 'show' | 'only';
  }) => {
    // Empty strings and 0 are left out, as before; empty arrays add nothing.
    const response = await api.get('/novels/search/', {
      params: {
        query: params.query || undefined,
        page: params.page || undefined,
        page_size: params.page_size || undefined,
        status: params.status || undefined,
        language: params.language || undefined,
        languages: params.languages,
        min_rating: params.min_rating || undefined,
        sort_by: params.sort_by || undefined,
        sort_order: params.sort_order || undefined,
        adult: params.adult || undefined,
        tag: params.tag,
        exclude_tag: params.exclude_tag,
        author: params.author,
      },
    });
    return response.data;
  },

  // Add this function to your novelService object
  getAutocompleteSuggestions: async (type: 'tag' | 'author', query: string): Promise<{ name: string; count: number }[]> => {
    const response = await api.get(`/novels/autocomplete/`, {
      params: {
        type,
        query,
        limit: 10
      }
    });
    return response.data;
  },

  // Get all home page data in a single request
  // `languages` filters every section to those content languages; when the
  // list is empty no language parameter is sent and the sections stay global.
  getHomePageData: async (languages: string[] = []) => {
    const response = await api.get('/novels/home/', { params: { languages } });
    return response.data;
  },

  // Get the image gallery for a source
  getSourceGallery: async (novelSlug: string, sourceSlug: string, page = 1, pageSize = 20) => {
    const response = await api.get(`/novels/${novelSlug}/${sourceSlug}/gallery/`, {
      params: { page, page_size: pageSize }
    });
    return response.data;
  },

  // Ask the backend to build the EPUB. Returns { status: 'ready' } when the file
  // can be downloaded right away, or { status: 'pending', job } when a background
  // job is building it (poll the job, then download once it completes).
  prepareSourceEpub: async (novelSlug: string, sourceSlug: string, volume?: number) => {
    const response = await api.post(
      `/novels/${encodeURIComponent(novelSlug)}/${encodeURIComponent(sourceSlug)}/download/prepare/`,
      null,
      { params: volume !== undefined ? { volume } : undefined },
    );
    return response.data;
  },

  // URL for downloading a source as EPUB once it is ready. Pass a volume to get
  // only that volume; omit it for the full novel. Used as a plain link, not via api.get.
  getSourceEpubUrl: (novelSlug: string, sourceSlug: string, volume?: number) => {
    const query = volume !== undefined ? `?volume=${volume}` : '';
    return `${API_BASE_URL}/novels/${encodeURIComponent(novelSlug)}/${encodeURIComponent(sourceSlug)}/download/${query}`;
  },
};
