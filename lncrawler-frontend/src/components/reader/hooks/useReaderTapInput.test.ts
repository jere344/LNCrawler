import { describe, it, expect, vi } from 'vitest';
import { decideTap, type TapInput } from './useReaderTapInput';

// A touch tap in the middle of a 1000px wide reader, with nothing open
const touchTap = (overrides: Partial<TapInput> = {}): TapInput => ({
  pointerType: 'touch',
  longPressFired: false,
  selectionCollapsed: true,
  onControl: false,
  panelOpen: false,
  controlsVisible: false,
  x: 500,
  width: 1000,
  leftEdge: 'chapter',
  rightEdge: 'chapter',
  trigger: 'singleTap',
  now: 10_000,
  lastTapAt: 0,
  lastHiddenAt: 0,
  seekTap: () => false,
  ...overrides,
});

describe('decideTap', () => {
  describe('mouse path', () => {
    it('closes an open panel before anything else', () => {
      const seekTap = vi.fn(() => true);
      expect(decideTap(touchTap({ pointerType: 'mouse', panelOpen: true, seekTap }))).toBe('closePanel');
      expect(seekTap).not.toHaveBeenCalled();
    });

    it('seeks when the tap lands on seekable text', () => {
      expect(decideTap(touchTap({ pointerType: 'mouse', seekTap: () => true }))).toBe('seek');
    });

    it('ignores a click that does not seek', () => {
      expect(decideTap(touchTap({ pointerType: 'mouse', seekTap: () => false }))).toBe('ignore');
    });

    it('never uses the edge zones or the controls trigger', () => {
      const input = touchTap({
        pointerType: 'mouse',
        x: 10,
        leftEdge: 'chapter',
        trigger: 'singleTap',
      });
      expect(decideTap(input)).toBe('ignore');
    });

    it('treats a keyboard click (no pointer type) like a mouse click', () => {
      expect(decideTap(touchTap({ pointerType: null, seekTap: () => true }))).toBe('seek');
      expect(decideTap(touchTap({ pointerType: null, panelOpen: true }))).toBe('closePanel');
    });
  });

  describe('touch rule order', () => {
    it('ignores a tap that ended a long press', () => {
      const seekTap = vi.fn(() => true);
      expect(decideTap(touchTap({ longPressFired: true, controlsVisible: true, seekTap }))).toBe('ignore');
      expect(seekTap).not.toHaveBeenCalled();
    });

    it('ignores a tap while text is selected', () => {
      expect(decideTap(touchTap({ selectionCollapsed: false, panelOpen: true }))).toBe('ignore');
    });

    it('ignores a tap on a control', () => {
      expect(decideTap(touchTap({ onControl: true, controlsVisible: true }))).toBe('ignore');
    });

    it('closes an open panel before hiding the controls', () => {
      expect(decideTap(touchTap({ panelOpen: true, controlsVisible: true }))).toBe('closePanel');
    });

    it('hides visible controls before reacting to edges or seeking', () => {
      const seekTap = vi.fn(() => true);
      expect(decideTap(touchTap({ controlsVisible: true, x: 10, seekTap }))).toBe('hideControls');
      expect(seekTap).not.toHaveBeenCalled();
    });

    it('runs the left edge action inside the 15% zone', () => {
      expect(decideTap(touchTap({ x: 150 }))).toBe('edgeLeft');
      expect(decideTap(touchTap({ x: 151 }))).toBe('showControls');
    });

    it('runs the right edge action inside the 15% zone', () => {
      expect(decideTap(touchTap({ x: 850 }))).toBe('edgeRight');
      expect(decideTap(touchTap({ x: 849 }))).toBe('showControls');
    });

    it('seeks the TTS on the centre when the text accepts it', () => {
      expect(decideTap(touchTap({ seekTap: () => true }))).toBe('seek');
    });

    it('shows the controls on a single tap in the centre', () => {
      expect(decideTap(touchTap({ trigger: 'singleTap' }))).toBe('showControls');
    });

    it('ignores centre taps when the trigger is off', () => {
      expect(decideTap(touchTap({ trigger: 'off' }))).toBe('ignore');
    });
  });

  describe('edge set to none', () => {
    it('falls through to the centre behaviour on the left', () => {
      expect(decideTap(touchTap({ x: 10, leftEdge: 'none', trigger: 'singleTap' }))).toBe('showControls');
    });

    it('falls through to the centre behaviour on the right', () => {
      expect(decideTap(touchTap({ x: 990, rightEdge: 'none', trigger: 'singleTap' }))).toBe('showControls');
    });

    it('still lets the seek happen when the edge falls through', () => {
      expect(decideTap(touchTap({ x: 10, leftEdge: 'none', seekTap: () => true }))).toBe('seek');
    });

    it('does not block the other edge', () => {
      expect(decideTap(touchTap({ x: 10, rightEdge: 'none' }))).toBe('edgeLeft');
      expect(decideTap(touchTap({ x: 990, leftEdge: 'none' }))).toBe('edgeRight');
    });
  });

  describe('double tap trigger', () => {
    const doubleTap = (overrides: Partial<TapInput>) => touchTap({ trigger: 'doubleTap', ...overrides });

    it('records the first tap', () => {
      expect(decideTap(doubleTap({ now: 10_000, lastTapAt: 0 }))).toBe('recordTap');
    });

    it('shows the controls when the second tap comes within 350ms', () => {
      expect(decideTap(doubleTap({ now: 10_000, lastTapAt: 9_700 }))).toBe('showControls');
    });

    it('records a second tap that comes too late', () => {
      expect(decideTap(doubleTap({ now: 10_000, lastTapAt: 9_650 }))).toBe('recordTap');
    });

    it('does not count the tap that hid the controls as the first of a double tap', () => {
      // The hide happened 200ms ago, so the next tap cannot pair with it
      expect(decideTap(doubleTap({ now: 10_000, lastTapAt: 9_900, lastHiddenAt: 9_800 }))).toBe('recordTap');
    });

    it('pairs taps again once the hide is older than the window', () => {
      expect(decideTap(doubleTap({ now: 10_000, lastTapAt: 9_900, lastHiddenAt: 9_000 }))).toBe('showControls');
    });
  });
});
