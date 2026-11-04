import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NovelChaptersResponse } from '@models/novels_types';
import { novelService } from '@services/novel.service';
import { chapterListCache } from './chapterList';
import { useChapterPages } from './useChapterPages';

vi.mock('@services/novel.service', () => ({
  novelService: { getNovelChapters: vi.fn() },
}));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

type Options = Parameters<typeof useChapterPages>[0];
type Hook = ReturnType<typeof useChapterPages>;

const getChapters = vi.mocked(novelService.getNovelChapters);
let roots: Root[] = [];

// A page of 35 chapters, or a search that finds 7; a chapter number asked with `around` is on page 3
const response = (page: number, search: string): NovelChaptersResponse => ({
  chapters: [{ id: `${search}-${page}`, chapter_id: page, title: '', url: '', volume: 0, volume_title: null, has_content: true }],
  count: search ? 7 : 35,
  total_pages: search ? 1 : 4,
  current_page: page,
  novel_title: 'Rising',
  source_name: 'site',
  is_dmca: false,
  has_volumes: false,
});

// Renders the hook into a probe component and returns a getter for its latest value, and a render with new options
const mount = (options: Options) => {
  const latest: { current: Hook | null } = { current: null };
  const Probe = (props: Options) => {
    latest.current = useChapterPages(props);
    return null;
  };
  const root = createRoot(document.createElement('div'));
  roots.push(root);
  const render = (props: Options) => act(() => root.render(createElement(Probe, props)));
  render(options);
  return { hook: () => latest.current as Hook, render };
};

// Lets the pending requests and the state updates they cause finish
const settle = () => act(async () => {
  await new Promise((resolve) => setTimeout(resolve, 0));
});

beforeEach(() => {
  getChapters.mockReset();
  getChapters.mockImplementation(async (_novel, _source, page = 1, _size, search = '', around) =>
    response(around === undefined ? page : 3, search));
});

afterEach(() => {
  roots.forEach((root) => act(() => root.unmount()));
  roots = [];
});

describe('useChapterPages', () => {
  it('shows a cached first page on the first render, with no request', async () => {
    await chapterListCache.load({ novelSlug: 'cached', sourceSlug: 'site', around: 25 });
    const { hook } = mount({ novelSlug: 'cached', sourceSlug: 'site', currentChapterId: 25, query: '' });
    expect(hook().view?.query).toBe('');
    expect(hook().view?.count).toBe(35);
    expect(getChapters).toHaveBeenCalledTimes(1);
  });

  it('keeps the old view and reports the failure when a new search fails', async () => {
    const { hook, render } = mount({ novelSlug: 'failing', sourceSlug: 'site', currentChapterId: 25, query: '' });
    await settle();
    getChapters.mockRejectedValueOnce(new Error('offline'));

    render({ novelSlug: 'failing', sourceSlug: 'site', currentChapterId: 25, query: 'dragon' });
    await settle();
    expect(hook().failed).toBe(true);
    expect(hook().view?.query).toBe('');
  });

  it('drops the first page of an older query that answers late', async () => {
    let answerDragon: (value: NovelChaptersResponse) => void = () => {};
    getChapters.mockImplementation(async (_novel, _source, page = 1, _size, search = '', around) => {
      if (search === 'dragon') return new Promise<NovelChaptersResponse>((resolve) => { answerDragon = resolve; });
      return response(around === undefined ? page : 3, search);
    });
    const { hook, render } = mount({ novelSlug: 'late', sourceSlug: 'site', currentChapterId: 25, query: '' });
    await settle();

    render({ novelSlug: 'late', sourceSlug: 'site', currentChapterId: 25, query: 'dragon' });
    render({ novelSlug: 'late', sourceSlug: 'site', currentChapterId: 25, query: 'elf' });
    await settle();
    expect(hook().view?.query).toBe('elf');

    answerDragon(response(1, 'dragon'));
    await settle();
    expect(hook().view?.query).toBe('elf');
  });
});
