import { describe, it, expect } from 'vitest';
import { dimBandMax, dimBandWidth, dimLevelFromDrag } from './readerGeometry';

describe('dimBandMax', () => {
  it('stops at 30% on narrow screens', () => {
    expect(dimBandMax(400)).toBe(30);
    expect(dimBandMax(600)).toBe(30);
  });

  it('shrinks in steps of 5 as the screen gets wider', () => {
    expect(dimBandMax(800)).toBe(25);
    expect(dimBandMax(1000)).toBe(20);
    expect(dimBandMax(1440)).toBe(10);
  });
});

describe('dimBandWidth', () => {
  it('keeps the saved width when it fits', () => {
    expect(dimBandWidth(15, 400)).toBe(15);
  });

  it('clamps the width in use without changing the saved value', () => {
    expect(dimBandWidth(25, 1440)).toBe(10);
    expect(dimBandWidth(25, 400)).toBe(25);
  });
});

describe('dimLevelFromDrag', () => {
  it('moves in steps of 5, downward is darker', () => {
    expect(dimLevelFromDrag(0, 40)).toBe(15);
    expect(dimLevelFromDrag(20, 120)).toBe(65);
    expect(dimLevelFromDrag(20, -40)).toBe(5);
  });

  it('stays between 0 and 90', () => {
    expect(dimLevelFromDrag(0, -500)).toBe(0);
    expect(dimLevelFromDrag(50, 500)).toBe(90);
  });
});
