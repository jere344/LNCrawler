import { describe, it, expect } from 'vitest';
import { normaliseSearchText, searchSettings, splitAtMatch } from './settingsSearch';

const item = (label: string, keywords = '', page = 'Text and layout') => ({ label, keywords, page });

describe('normaliseSearchText', () => {
  it('drops accents and case', () => {
    expect(normaliseSearchText('Café Crème')).toBe('cafe creme');
  });
});

describe('searchSettings', () => {
  it('returns nothing for a blank query', () => {
    expect(searchSettings('   ', [item('Font')])).toEqual([]);
  });

  it('ignores accents and case in the query', () => {
    const items = [item('Café')];
    expect(searchSettings('CAFE', items)).toEqual(items);
  });

  it('requires every word to match the label, keywords or page name', () => {
    const items = [item('Font', 'typeface dyslexic'), item('Speed', 'listen rate')];
    expect(searchSettings('dyslexic font', items)).toEqual([items[0]]);
    expect(searchSettings('dyslexic speed', items)).toEqual([]);
  });

  it('matches the page name', () => {
    const items = [item('Left arrow', 'keyboard key', 'Keyboard')];
    expect(searchSettings('keyboard arrow', items)).toEqual(items);
  });

  it('ranks label starts, then label contains, then keyword matches', () => {
    const keywordOnly = item('Pause', 'size');
    const labelInside = item('Text size', '');
    const labelStart = item('Size of text', '');
    expect(searchSettings('size', [keywordOnly, labelInside, labelStart])).toEqual([labelStart, labelInside, keywordOnly]);
  });

  it('keeps the index order within the same rank', () => {
    const first = item('Night filter', 'warm');
    const second = item('Night schedule', 'warm');
    expect(searchSettings('warm', [first, second])).toEqual([first, second]);
  });
});

describe('splitAtMatch', () => {
  it('splits the label around the match, keeping its case', () => {
    expect(splitAtMatch('Text size', 'SIZE')).toEqual({ before: 'Text ', match: 'size', after: '' });
  });

  it('returns null without a plain match', () => {
    expect(splitAtMatch('Font', 'dyslexic')).toBeNull();
    expect(splitAtMatch('Font', '  ')).toBeNull();
  });
});
