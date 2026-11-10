import { describe, expect, it } from 'vitest';
import type { NovelFromSource } from '@models/novels_types';
import { ALL, defaultLanguage, facetCounts, matchesFilters, sortSources } from './sourceFilters';

const make = (slug: string, extra: Partial<NovelFromSource> = {}): NovelFromSource =>
  ({
    source_slug: slug,
    source_name: slug,
    title: 'Shadow Slave',
    language: 'en',
    edition: null,
    chapters_count: 10,
    vote_score: 0,
    last_chapter_update: '2026-01-01T00:00:00Z',
    latest_available_chapter: null,
    ...extra,
  }) as NovelFromSource;

describe('defaultLanguage', () => {
  it('starts on the current source language when another source shares it', () => {
    expect(defaultLanguage([make('a'), make('b', { language: 'es' })], make('cur'))).toBe('en');
  });

  it('falls back to all when no other source shares it', () => {
    expect(defaultLanguage([make('b', { language: 'es' })], make('cur'))).toBe(ALL);
    expect(defaultLanguage([make('b')], undefined)).toBe(ALL);
  });
});

describe('matchesFilters', () => {
  const filters = { query: '', language: ALL, edition: ALL };

  it('filters by language, edition and a search over name, title and last chapter', () => {
    const s = make('novelbin.me', { edition: 'Light Novel', latest_available_chapter: { display_title: 'Royal Tantrum' } as never });
    expect(matchesFilters(s, filters)).toBe(true);
    expect(matchesFilters(s, { ...filters, language: 'es' })).toBe(false);
    expect(matchesFilters(s, { ...filters, edition: 'light novel' })).toBe(true);
    expect(matchesFilters(s, { ...filters, edition: 'web novel' })).toBe(false);
    expect(matchesFilters(s, { ...filters, query: 'tantrum' })).toBe(true);
    expect(matchesFilters(s, { ...filters, query: 'nothing' })).toBe(false);
  });
});

describe('facetCounts', () => {
  it('counts one facet with the other filters applied', () => {
    const sources = [make('a'), make('b', { edition: 'LN' }), make('c', { language: 'es', edition: 'LN' })];
    const counts = facetCounts(sources, { query: '', language: 'en', edition: ALL }, 'edition');
    expect(counts.get('ln')).toBe(1);
    expect(counts.get('')).toBe(1);
  });
});

describe('sortSources', () => {
  it('sorts on the ratings it was given, not the live vote score', () => {
    const a = make('a', { vote_score: 9 });
    const b = make('b', { vote_score: 1 });
    expect(sortSources([a, b], 'rating', 'desc', { a: 0, b: 5 }).map((s) => s.source_slug)).toEqual(['b', 'a']);
  });

  it('sorts by name ascending, ignoring a leading www., and reverses', () => {
    const sources = [make('www.b.com'), make('a.com')];
    expect(sortSources(sources, 'name', 'asc', {}).map((s) => s.source_slug)).toEqual(['a.com', 'www.b.com']);
    expect(sortSources(sources, 'name', 'desc', {}).map((s) => s.source_slug)).toEqual(['www.b.com', 'a.com']);
  });
});
