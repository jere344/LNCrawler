import { describe, it, expect } from 'vitest';
import { fitsInSheet, pairRows, sheetHeight } from './displayLayout';
import { READER_BOTTOM_BAR_HEIGHT } from '../controls/readerBarTypes';

describe('pairRows', () => {
  it('puts two consecutive half modules on one line', () => {
    expect(pairRows(['size', 'line', 'theme', 'font'])).toEqual([['size', 'line'], ['theme'], ['font']]);
  });

  it('keeps a half module alone when the next one is full width', () => {
    expect(pairRows(['size', 'theme', 'line'])).toEqual([['size'], ['theme'], ['line']]);
  });

  it('returns no rows for no modules', () => {
    expect(pairRows([])).toEqual([]);
  });
});

describe('sheetHeight', () => {
  it('is the header and padding when there are no modules', () => {
    expect(sheetHeight([])).toBe(44 + 14);
  });

  it('adds each row at its tallest module plus the gap', () => {
    // One paired row (48 + 10) and one theme row (62 + 10), on top of header and padding
    expect(sheetHeight(['size', 'line', 'theme'])).toBe(44 + (48 + 10) + (62 + 10) + 14);
  });
});

describe('fitsInSheet', () => {
  it('always fits on phone landscape and desktop', () => {
    const many = ['size', 'line', 'para', 'margin', 'indent', 'align', 'theme', 'font', 'dim', 'warm'] as const;
    expect(fitsInSheet([...many], 200, 'desktop')).toBe(true);
    expect(fitsInSheet([...many], 200, 'phoneLandscape')).toBe(true);
  });

  it('fits a short default sheet on a phone', () => {
    expect(fitsInSheet(['size', 'line', 'theme', 'font', 'dim', 'warm'], 800, 'phone')).toBe(true);
  });

  it('rejects a full sheet on a short phone', () => {
    const many = ['size', 'line', 'para', 'margin', 'indent', 'align', 'theme', 'font', 'dim', 'warm'] as const;
    expect(fitsInSheet([...many], 500, 'phone')).toBe(false);
  });

  it('counts the tablet bottom bar against the viewport', () => {
    // Five rows of 58 plus header and padding = 348. With the bottom bar it is exactly 58% of an 807px viewport on a tablet
    const modules = ['size', 'line', 'para', 'margin', 'indent', 'align', 'font'] as const;
    const height = sheetHeight([...modules]);
    const viewport = Math.ceil((height + READER_BOTTOM_BAR_HEIGHT) / 0.58);
    expect(fitsInSheet([...modules], viewport, 'tablet')).toBe(true);
    expect(fitsInSheet([...modules], viewport - 60, 'tablet')).toBe(false);
    expect(fitsInSheet([...modules], viewport - 60, 'phone')).toBe(true);
  });
});
