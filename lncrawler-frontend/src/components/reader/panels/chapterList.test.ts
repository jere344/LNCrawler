import { describe, expect, it } from 'vitest';
import type { NovelChaptersResponse } from '@models/novels_types';
import { chapterIndex, pageRange } from './chapterList';

// A page of the unfiltered list with the given chapter numbers
const page = (current_page: number, chapterIds: number[]): NovelChaptersResponse => ({
  chapters: chapterIds.map((chapter_id) => ({ id: `${chapter_id}`, chapter_id, title: '', display_title: '', url: '', volume: 0, volume_title: null, has_content: true })),
  count: 350,
  total_pages: 4,
  current_page,
  novel_title: 'Rising',
  source_name: 'site',
  is_dmca: false,
  has_volumes: false,
});

describe('pageRange', () => {
  it('is empty for an empty list or an empty range', () => {
    expect(pageRange(0, 10, 0)).toEqual([1, 0]);
    expect(pageRange(50, 50, 350)).toEqual([1, 0]);
  });

  it('gives the first page for rows at the top', () => {
    expect(pageRange(0, 10, 350)).toEqual([1, 1]);
  });

  it('spans two pages when the rows cross a page boundary', () => {
    expect(pageRange(95, 105, 350)).toEqual([1, 2]);
  });

  it('clamps the end to the count', () => {
    expect(pageRange(300, 500, 350)).toEqual([4, 4]);
  });
});

describe('chapterIndex', () => {
  it('gives the index in the whole list of a chapter on page 3', () => {
    expect(chapterIndex(page(3, [201, 202, 203]), 202)).toBe(201);
  });

  it('gives null when the chapter is not on the page', () => {
    expect(chapterIndex(page(3, [201, 202, 203]), 999)).toBeNull();
  });
});
