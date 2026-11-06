import { describe, expect, it } from 'vitest';
import { pickActiveSection, type SectionBounds } from './activeSection';

const LINE = 100;

// Three sections stacked down the page: the second one spans the reading line
const SECTIONS: SectionBounds[] = [
  { key: 'a', top: -800, bottom: -200 },
  { key: 'b', top: -150, bottom: 400 },
  { key: 'c', top: 400, bottom: 900 },
];

describe('pickActiveSection', () => {
  it('is null for an empty list', () => {
    expect(pickActiveSection([], LINE)).toBeNull();
  });

  it('picks the first section when all are below the line', () => {
    const below: SectionBounds[] = [
      { key: 'a', top: 300, bottom: 700 },
      { key: 'b', top: 700, bottom: 1100 },
    ];
    expect(pickActiveSection(below, LINE)).toBe('a');
  });

  it('picks the section that spans the line', () => {
    expect(pickActiveSection(SECTIONS, LINE)).toBe('b');
  });

  it('picks the section whose top is exactly at the line', () => {
    const atLine: SectionBounds[] = [
      { key: 'a', top: -500, bottom: 100 },
      { key: 'b', top: LINE, bottom: 600 },
    ];
    expect(pickActiveSection(atLine, LINE)).toBe('b');
  });

  it('picks the last section when scrolled past all of them', () => {
    const past: SectionBounds[] = [
      { key: 'a', top: -1500, bottom: -900 },
      { key: 'b', top: -900, bottom: -300 },
    ];
    expect(pickActiveSection(past, LINE)).toBe('b');
  });
});
