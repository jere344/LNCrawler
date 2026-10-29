import api, { getCsrfToken } from './api';
import { API_BASE_URL } from './config';
import {
  AudiobookDetail,
  AudiobookFormat,
  AudiobookListParams,
  AudiobookListResponse,
  AudiobookPlayBody,
  AudiobookPrepareResult,
  ListeningProgress,
  ListeningProgressUpdate,
} from '@models/audiobook_types';

// Seconds to wait when the backend sends no usable Retry-After header.
const DEFAULT_RETRY_S = 5;

// Lang is only sent for non-English viewers: English is the backend default.
const withLang = (params: URLSearchParams, lang: string) => {
  if (lang !== 'en') params.append('lang', lang);
  return params;
};

const retryAfterOf = (headers: Headers): number => {
  const seconds = Number(headers.get('Retry-After'));
  return Number.isFinite(seconds) && seconds > 0 ? seconds : DEFAULT_RETRY_S;
};

const progressPath = (slug: string, lang: string) =>
  `/audiobooks/${encodeURIComponent(slug)}/progress/?${withLang(new URLSearchParams(), lang)}`;

const downloadPath = (slug: string, lang: string, index: number, format: AudiobookFormat) => {
  const params = new URLSearchParams({ format });
  return `/audiobooks/${encodeURIComponent(slug)}/parts/${index}/download/?${withLang(params, lang)}`;
};

// Plain download URL of a part file. Open to everyone, so a hidden anchor can fetch it without a token.
export const downloadUrl = (slug: string, lang: string, index: number, format: AudiobookFormat): string =>
  `${API_BASE_URL}${downloadPath(slug, lang, index, format)}`;

export const audiobookService = {
  // Visible audiobooks, paginated, with the sort and filters of the list page.
  list: async (params: AudiobookListParams = {}): Promise<AudiobookListResponse> => {
    const query = new URLSearchParams();
    if (params.sort) query.append('sort', params.sort);
    if (params.q) query.append('q', params.q);
    params.tag?.forEach((tag) => query.append('tag', tag));
    params.exclude_tag?.forEach((tag) => query.append('exclude_tag', tag));
    params.author?.forEach((author) => query.append('author', author));
    if (params.listening) query.append('listening', '1');
    if (params.page) query.append('page', String(params.page));
    if (params.page_size) query.append('page_size', String(params.page_size));
    withLang(query, params.lang ?? 'en');
    const response = await api.get(`/audiobooks/?${query}`);
    return response.data;
  },

  detail: async (slug: string, lang: string): Promise<AudiobookDetail> => {
    const query = withLang(new URLSearchParams(), lang);
    const response = await api.get(`/audiobooks/${encodeURIComponent(slug)}/?${query}`);
    return response.data;
  },

  // The viewer's progress, null when they have none. Requires auth.
  getProgress: async (slug: string, lang: string): Promise<ListeningProgress | null> => {
    const response = await api.get(progressPath(slug, lang));
    return response.data.progress;
  },

  saveProgress: async (slug: string, lang: string, body: ListeningProgressUpdate): Promise<ListeningProgress | null> => {
    const response = await api.put(progressPath(slug, lang), body);
    return response.data.progress;
  },

  // Fire-and-forget save for pagehide and visibilitychange, where the page may be gone before
  // a normal request could finish. `keepalive` lets the browser send it after unload.
  saveProgressOnHide: (slug: string, lang: string, body: ListeningProgressUpdate): void => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...api.defaults.headers.common,
    };
    const csrfToken = getCsrfToken();
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;
    fetch(`${API_BASE_URL}${progressPath(slug, lang)}`, {
      method: 'POST',
      headers,
      credentials: 'include',
      keepalive: true,
      body: JSON.stringify(body),
    }).catch(() => {
      // Best effort: the next periodic save or the next visit catches up.
    });
  },

  // Counts a play. Errors are swallowed: a missed count must not disturb listening.
  play: async (slug: string, lang: string, body: AudiobookPlayBody): Promise<void> => {
    const query = withLang(new URLSearchParams(), lang);
    try {
      await api.post(`/audiobooks/${encodeURIComponent(slug)}/play/?${query}`, body);
    } catch {
      // ignored on purpose, see above
    }
  },

  // Asks the backend whether a part file is cached (`check=1`: no serve, no count). When it is not,
  // the build starts as usual. The caller then triggers the real download with a hidden anchor (see downloadUrl).
  // Network and server errors are thrown to the caller.
  prepare: async (
    slug: string,
    lang: string,
    index: number,
    format: AudiobookFormat,
  ): Promise<AudiobookPrepareResult> => {
    const path = `${downloadPath(slug, lang, index, format)}&check=1`;
    const response = await api.get(path);
    if (response.status === 200) {
      return { status: 'ready', url: downloadUrl(slug, lang, index, format) };
    }
    return {
      status: 'building',
      progress: typeof response.data?.progress === 'number' ? response.data.progress : null,
      retryAfter: retryAfterOf(response.headers),
    };
  },
};
