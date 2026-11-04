import { describe, expect, it } from 'vitest';
import { rowWindow } from './useVirtualRows';

const ROW = 48;

describe('rowWindow', () => {
  it('is empty for an empty list', () => {
    expect(rowWindow(0, 480, 0, ROW)).toEqual({ top: 0, start: 0, end: 0 });
  });

  it('renders the rows in view with a screen of overscan on each side', () => {
    expect(rowWindow(960, 240, 100, ROW)).toEqual({ top: 20, start: 10, end: 35 });
  });

  it('clamps the overscan at the first row', () => {
    expect(rowWindow(0, 480, 100, ROW)).toEqual({ top: 0, start: 0, end: 20 });
  });

  it('clamps the overscan at the last row', () => {
    expect(rowWindow(2400, 480, 60, ROW)).toEqual({ top: 50, start: 40, end: 60 });
  });

  it('keeps the top row on the last row when scrolled past the end', () => {
    expect(rowWindow(100000, 480, 10, ROW)).toEqual({ top: 9, start: 0, end: 10 });
  });
});
