import { describe, expect, it } from 'vitest';
import { pagesIn, progressIn, scrollYFor, type ScrollRange } from './chapterRange';

// A section starting 1000px down the page, 3000px tall in a 800px viewport
const RANGE: ScrollRange = { start: 1000, length: 2200, height: 3000 };

describe('progressIn', () => {
  it('is 0 at the start and 1 at the end of the range', () => {
    expect(progressIn(RANGE, 1000)).toBe(0);
    expect(progressIn(RANGE, 3200)).toBe(1);
  });

  it('is the share of the range scrolled past', () => {
    expect(progressIn(RANGE, 2100)).toBeCloseTo(0.5);
  });

  it('clamps to 0..1 outside the range', () => {
    expect(progressIn(RANGE, 0)).toBe(0);
    expect(progressIn(RANGE, 9999)).toBe(1);
  });

  it('is 0 when the range has nothing to scroll', () => {
    expect(progressIn({ start: 500, length: 0, height: 400 }, 900)).toBe(0);
    expect(progressIn({ start: 500, length: -120, height: 400 }, 500)).toBe(0);
  });

  it('matches the chapter-mode percentage of the whole document', () => {
    // The old formula: scrollY / (scrollHeight - clientHeight), with the document starting at 0
    const scrollHeight = 5000;
    const clientHeight = 800;
    const documentRange: ScrollRange = { start: 0, length: scrollHeight - clientHeight, height: scrollHeight };
    for (const scrollY of [0, 150, 2100, 4200]) {
      expect(progressIn(documentRange, scrollY)).toBe(scrollY / (scrollHeight - clientHeight));
    }
  });
});

describe('scrollYFor', () => {
  it('is the start at progress 0 and the end at progress 1', () => {
    expect(scrollYFor(RANGE, 0)).toBe(1000);
    expect(scrollYFor(RANGE, 1)).toBe(3200);
  });

  it('places the window part way through the range', () => {
    expect(scrollYFor(RANGE, 0.25)).toBe(1550);
  });

  it('stays at the start when the range has nothing to scroll', () => {
    expect(scrollYFor({ start: 500, length: -120, height: 400 }, 0.8)).toBe(500);
  });

  it('round-trips with progressIn', () => {
    expect(progressIn(RANGE, scrollYFor(RANGE, 0.4))).toBeCloseTo(0.4);
  });
});

describe('pagesIn', () => {
  it('counts the screens the range takes', () => {
    expect(pagesIn(RANGE, 800, 1000)).toEqual({ page: 1, pages: 4 });
    expect(pagesIn({ start: 0, length: 1600, height: 2400 }, 800, 0)).toEqual({ page: 1, pages: 3 });
  });

  it('gives the screen the window is on', () => {
    expect(pagesIn(RANGE, 800, 1000 + 800)).toEqual({ page: 2, pages: 4 });
    expect(pagesIn(RANGE, 800, 1000 + 1700)).toEqual({ page: 3, pages: 4 });
  });

  it('is at least one page', () => {
    expect(pagesIn({ start: 0, length: 0, height: 0 }, 800, 0)).toEqual({ page: 1, pages: 1 });
  });

  it('clamps the page to the first and last screen', () => {
    expect(pagesIn(RANGE, 800, 0)).toEqual({ page: 1, pages: 4 });
    expect(pagesIn(RANGE, 800, 99999)).toEqual({ page: 4, pages: 4 });
  });

  it('does not divide by zero before the viewport is laid out', () => {
    expect(pagesIn({ start: 0, length: 0, height: 900 }, 0, 0)).toEqual({ page: 1, pages: 900 });
  });
});
