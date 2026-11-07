import { describe, expect, it } from 'vitest';
import type { LibrarySource, NovelFromSource } from '@models/novels_types';
import { isFullSource } from './sourceView';

// What a library card sends: the preview columns only.
const preview: LibrarySource = {
  title: 'Preview',
  source_slug: 'src',
  novel_slug: 'novel',
  novel_id: 'novel-1',
  cover_min_url: null,
  available_chapters_count: 3,
  latest_available_chapter: null,
  is_adult: false,
};

// A summary-shaped source (the novel detail's nested sources): counters, but no authors or tags.
const summary: LibrarySource & Pick<NovelFromSource, 'chapters_count' | 'vote_score'> = {
  ...preview,
  chapters_count: 3,
  vote_score: 0,
};

// A full source, as the detail fetch or a home card's state carries it.
const full: NovelFromSource = {
  ...preview,
  id: 'source-1',
  source_url: 'https://example.com/novel',
  source_name: 'Example',
  edition: null,
  has_crawler: true,
  cover_path: null,
  cover_url: null,
  authors: ['Author'],
  tags: ['Fantasy'],
  language: 'en',
  status: 'Ongoing',
  synopsis: null,
  chapters_count: 3,
  last_chapter_update: '2026-01-01T00:00:00Z',
  upvotes: 0,
  downvotes: 0,
  vote_score: 0,
  user_vote: null,
  novel_title: 'Novel',
  overview_url: null,
  first_available_chapter: null,
  novelupdates_url: null,
  editors: [],
  translators: [],
  alternative_titles: [],
  original_publisher: null,
  english_publisher: null,
};

describe('isFullSource', () => {
  it('treats a library preview as a preview', () => {
    expect(isFullSource(preview)).toBe(false);
  });

  it('treats a summary-shaped source (counters, no authors) as a preview', () => {
    expect(isFullSource(summary)).toBe(false);
  });

  it('treats the detail fetch or a card source as full', () => {
    expect(isFullSource(full)).toBe(true);
  });

  it('is false without a source', () => {
    expect(isFullSource(null)).toBe(false);
    expect(isFullSource(undefined)).toBe(false);
  });
});
