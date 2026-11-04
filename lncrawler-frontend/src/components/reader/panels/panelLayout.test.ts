import { describe, expect, it } from 'vitest';
import {
  CHAPTER_LIST_WIDTH,
  commentsWidth,
  panelWidth,
  reservedEnd,
  reservedMargin,
  reservedStart,
} from './panelLayout';

describe('panelWidth', () => {
  it('covers the whole screen on phones', () => {
    expect(panelWidth('phone')).toBeNull();
  });

  it('is 400px on tablets and phone landscape', () => {
    expect(panelWidth('tablet')).toBe(400);
    expect(panelWidth('phoneLandscape')).toBe(400);
  });

  it('is 600px on desktop', () => {
    expect(panelWidth('desktop')).toBe(600);
  });
});

describe('commentsWidth', () => {
  it('covers the whole screen on phones', () => {
    expect(commentsWidth('phone')).toBeNull();
  });

  it('is 400px on tablets and phone landscape', () => {
    expect(commentsWidth('tablet')).toBe(400);
    expect(commentsWidth('phoneLandscape')).toBe(400);
  });

  it('is 440px on desktop, narrower than the settings panel', () => {
    expect(commentsWidth('desktop')).toBe(440);
    expect(commentsWidth('desktop')).toBeLessThan(panelWidth('desktop') ?? 0);
  });
});

describe('reservedEnd', () => {
  it('reserves 360px for the display sheet on phone landscape only', () => {
    expect(reservedEnd('display', 'phoneLandscape')).toBe(360);
    expect(reservedEnd('display', 'tablet')).toBe(0);
    expect(reservedEnd('display', 'desktop')).toBe(0);
  });

  it('reserves the panel width for settings and customize off phones', () => {
    expect(reservedEnd('settings', 'tablet')).toBe(400);
    expect(reservedEnd('settings', 'phoneLandscape')).toBe(400);
    expect(reservedEnd('settings', 'desktop')).toBe(600);
    expect(reservedEnd('customize', 'desktop')).toBe(600);
  });

  it('reserves the comments panel width off phones', () => {
    expect(reservedEnd('comments', 'tablet')).toBe(400);
    expect(reservedEnd('comments', 'phoneLandscape')).toBe(400);
    expect(reservedEnd('comments', 'desktop')).toBe(440);
  });

  it('reserves nothing on phones or with no panel open', () => {
    expect(reservedEnd('settings', 'phone')).toBe(0);
    expect(reservedEnd('customize', 'phone')).toBe(0);
    expect(reservedEnd('comments', 'phone')).toBe(0);
    expect(reservedEnd('none', 'desktop')).toBe(0);
  });
});

describe('reservedStart', () => {
  it('reserves the chapter list width at the start edge off phones', () => {
    expect(CHAPTER_LIST_WIDTH).toBe(360);
    expect(reservedStart('chapters', 'tablet')).toBe(360);
    expect(reservedStart('chapters', 'phoneLandscape')).toBe(360);
    expect(reservedStart('chapters', 'desktop')).toBe(360);
  });

  it('reserves nothing on phones, where the list overlays the text, or with another panel open', () => {
    expect(reservedStart('chapters', 'phone')).toBe(0);
    expect(reservedStart('display', 'desktop')).toBe(0);
    expect(reservedStart('settings', 'desktop')).toBe(0);
    expect(reservedStart('none', 'desktop')).toBe(0);
  });
});

describe('reservedMargin', () => {
  it('is 0 when nothing is reserved', () => {
    expect(reservedMargin(0)).toBe(0);
  });

  it('subtracts the centred gutter of the 1200px container from the reserved width', () => {
    expect(reservedMargin(600)).toBe('max(0px, calc(600px - max(0px, (100vw - 1200px) / 2)))');
  });
});
