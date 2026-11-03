import { describe, it, expect, vi } from 'vitest';
import type { NovelChaptersResponse } from '@models/novels_types';
import { CHAPTER_LIST_TTL_MS, createChapterListCache, type ChapterPageRequest } from './chapterListCache';

// A source of 35 chapters, 10 per page; `around` answers the page holding the chapter number
const response = (page: number, search = ''): NovelChaptersResponse => ({
  chapters: [{ id: `${search}${page}`, chapter_id: page, title: '', url: '', volume: 0, volume_title: null, has_content: true }],
  count: search ? 7 : 35,
  total_pages: search ? 1 : 4,
  current_page: page,
  novel_title: 'Rising',
  source_name: 'site',
  is_dmca: false,
  has_volumes: false,
});

const setup = () => {
  let clock = 0;
  const fetchPage = vi.fn(async (request: ChapterPageRequest) => {
    if (request.around !== undefined) return response(Math.ceil(request.around / 10) || 1);
    return response(request.page ?? 1, request.search);
  });
  const cache = createChapterListCache(fetchPage, () => clock);
  const request = { novelSlug: 'rising', sourceSlug: 'site' };
  return { cache, fetchPage, request, advance: (ms: number) => { clock += ms; } };
};

describe('chapterListCache', () => {
  it('reopening within the TTL at the same chapter makes no request', async () => {
    const { cache, fetchPage, request } = setup();
    await cache.load({ ...request, around: 25 });
    await cache.load({ ...request, around: 25 });
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });

  it('a page loaded before is not fetched again, even when opened by another chapter', async () => {
    const { cache, fetchPage, request } = setup();
    await cache.load({ ...request, around: 25 }); // page 3
    const again = await cache.load({ ...request, page: 3 });
    expect(again.current_page).toBe(3);
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });

  it('refetches a listing older than the TTL on the next open', async () => {
    const { cache, fetchPage, request, advance } = setup();
    await cache.load({ ...request, around: 25 });
    advance(CHAPTER_LIST_TTL_MS);
    await cache.load({ ...request, around: 25 });
    expect(fetchPage).toHaveBeenCalledTimes(2);
  });

  it('shares one in-flight request between concurrent callers', async () => {
    const { cache, fetchPage, request } = setup();
    const [a, b] = await Promise.all([
      cache.load({ ...request, page: 2 }),
      cache.load({ ...request, page: 2 }),
    ]);
    expect(a).toBe(b);
    expect(fetchPage).toHaveBeenCalledTimes(1);
  });

  it('does not cache a failed request', async () => {
    const { cache, fetchPage, request } = setup();
    fetchPage.mockRejectedValueOnce(new Error('offline'));
    await expect(cache.load({ ...request, page: 2 })).rejects.toThrow('offline');
    await cache.load({ ...request, page: 2 });
    expect(fetchPage).toHaveBeenCalledTimes(2);
  });

  it('keeps search results per query', async () => {
    const { cache, fetchPage, request } = setup();
    await cache.load({ ...request, search: 'dragon' });
    await cache.load({ ...request, search: 'elf' });
    await cache.load({ ...request, search: ' dragon ' });
    expect(fetchPage).toHaveBeenCalledTimes(2);
  });

  it('ignores around while searching and loads page 1 of the results', async () => {
    const { cache, fetchPage, request } = setup();
    const result = await cache.load({ ...request, search: 'Chapter 3', around: 25 });
    expect(result.current_page).toBe(1);
    expect(fetchPage).toHaveBeenCalledWith(expect.objectContaining({ page: 1, search: 'Chapter 3' }));
  });

  it('keeps each source in its own listing', async () => {
    const { cache, fetchPage, request } = setup();
    await cache.load({ ...request, page: 1 });
    await cache.load({ ...request, sourceSlug: 'other', page: 1 });
    expect(fetchPage).toHaveBeenCalledTimes(2);
  });
});
