import { describe, expect, it } from 'vitest';
import { SHEET_SNAP_DISTANCE, SHEET_TAP_DISTANCE, sheetDragResult } from './sheetDrag';

describe('sheetDragResult', () => {
  it('expands on a drag up past the snap distance, whether full or not', () => {
    expect(sheetDragResult(-(SHEET_SNAP_DISTANCE + 1), false)).toBe('expand');
    expect(sheetDragResult(-(SHEET_SNAP_DISTANCE + 1), true)).toBe('expand');
  });

  it('closes a partial sheet on a drag down past the snap distance', () => {
    expect(sheetDragResult(SHEET_SNAP_DISTANCE + 1, false)).toBe('close');
  });

  it('shrinks a full sheet on a drag down past the snap distance', () => {
    expect(sheetDragResult(SHEET_SNAP_DISTANCE + 1, true)).toBe('shrink');
  });

  it('closes the composer on a drag down past the snap distance, whether the sheet is full or not', () => {
    expect(sheetDragResult(SHEET_SNAP_DISTANCE + 1, false, true)).toBe('stopComposing');
    expect(sheetDragResult(SHEET_SNAP_DISTANCE + 1, true, true)).toBe('stopComposing');
  });

  it('toggles on a tap, in either direction within the tap distance', () => {
    expect(sheetDragResult(0, false)).toBe('toggle');
    expect(sheetDragResult(SHEET_TAP_DISTANCE - 1, true)).toBe('toggle');
    expect(sheetDragResult(-(SHEET_TAP_DISTANCE - 1), false)).toBe('toggle');
  });

  it('does nothing for a drag between a tap and the snap distance', () => {
    expect(sheetDragResult(SHEET_TAP_DISTANCE, false)).toBeNull();
    expect(sheetDragResult(-SHEET_TAP_DISTANCE, true)).toBeNull();
    expect(sheetDragResult(SHEET_SNAP_DISTANCE, false)).toBeNull();
    expect(sheetDragResult(-SHEET_SNAP_DISTANCE, true)).toBeNull();
  });
});
