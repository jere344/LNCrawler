import { useEffect, useRef, type HTMLAttributes, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent } from 'react';
import type { CenterAction, EdgeTapBehavior, ReaderSettings } from '../readerSettingsSchema';

const EDGE_TAP_WIDTH_PERCENTAGE = 15; // % of screen width for edge tap detection
const DOUBLE_TAP_MS = 350;
const LONG_PRESS_MS = 500;
const LONG_PRESS_MOVE_PX = 10; // A press that moves further than this is a scroll, not a long press
// Taps on these keep their own behaviour
const CONTROL_SELECTOR = 'a, button, input, select, textarea, [role="button"]';

export type ReaderTapProps = Pick<
  HTMLAttributes<HTMLDivElement>,
  'onClick' | 'onPointerDown' | 'onPointerMove' | 'onPointerUp' | 'onPointerCancel' | 'onContextMenu'
>;

export interface TapInput {
  // null when no press was recorded (a click from the keyboard)
  pointerType: string | null;
  longPressFired: boolean;
  selectionCollapsed: boolean;
  onControl: boolean;
  panelOpen: boolean;
  controlsVisible: boolean;
  x: number;
  width: number;
  leftEdge: EdgeTapBehavior;
  rightEdge: EdgeTapBehavior;
  singleTap: CenterAction;
  doubleTap: CenterAction;
  now: number;
  lastTapAt: number;
  lastHiddenAt: number;
  // Seeks the TTS to the tapped text; true when it did
  seekTap: () => boolean;
}

type TapAction =
  | 'ignore'
  | 'closePanel'
  | 'hideControls'
  | 'edgeLeft'
  | 'edgeRight'
  | 'seek'
  | 'fullscreen'
  | 'showControls'
  | 'recordTap';

// Which action a click performs. The order of the checks is the behaviour: only seekTap has a side effect here.
export function decideTap(input: TapInput): TapAction {
  // A mouse never uses the tap zones or the controls trigger
  if (input.pointerType === null || input.pointerType === 'mouse') {
    if (input.panelOpen) return 'closePanel';
    return input.seekTap() ? 'seek' : 'ignore';
  }

  if (input.longPressFired || !input.selectionCollapsed || input.onControl) return 'ignore';
  if (input.panelOpen) return 'closePanel';

  const edgeWidth = input.width * (EDGE_TAP_WIDTH_PERCENTAGE / 100);
  // An edge set to 'none' falls through to the centre behaviour
  const inCenter = (input.x > edgeWidth || input.leftEdge === 'none') && (input.x < input.width - edgeWidth || input.rightEdge === 'none');

  // Checked before the controls: the first tap of a double tap already did its own single-tap action
  if (inCenter && input.doubleTap !== 'none' && input.now - input.lastTapAt < DOUBLE_TAP_MS) {
    if (input.doubleTap === 'fullscreen') return 'fullscreen';
    // The tap that hid the controls must not count as the first of a double tap
    if (input.now - input.lastHiddenAt > DOUBLE_TAP_MS) return input.controlsVisible ? 'hideControls' : 'showControls';
  }

  if (input.controlsVisible) return 'hideControls';

  if (input.x <= edgeWidth && input.leftEdge !== 'none') return 'edgeLeft';
  if (input.x >= input.width - edgeWidth && input.rightEdge !== 'none') return 'edgeRight';

  if (input.seekTap()) return 'seek';

  if (input.singleTap === 'controls') return 'showControls';
  if (input.singleTap === 'fullscreen') return 'fullscreen';
  // Nothing to do, but it can be the first tap of a double tap
  return 'recordTap';
}

interface TapOptions {
  settings: Pick<ReaderSettings, 'centerSingleTap' | 'centerDoubleTap' | 'centerLongPress' | 'leftEdgeTapBehavior' | 'rightEdgeTapBehavior'>;
  controlsVisible: boolean;
  panelOpen: boolean;
  setControlsVisible: (visible: boolean) => void;
  closePanel: () => void;
  onEdge: (edge: 'left' | 'right', behavior: EdgeTapBehavior) => void;
  seekTap: (target: Node) => boolean;
  onFullscreen: () => void;
}

// Touch and mouse input on the text. Returns the props for the reader viewport.
export function useReaderTapInput({
  settings,
  controlsVisible,
  panelOpen,
  setControlsVisible,
  closePanel,
  onEdge,
  seekTap,
  onFullscreen,
}: TapOptions): { tapProps: ReaderTapProps; tapAt: (x: number, width: number, target: EventTarget) => void } {
  const pointerTypeRef = useRef<string | null>(null);
  const longPressFiredRef = useRef(false);
  const longPressTimerRef = useRef<number | null>(null);
  const pressStartRef = useRef({ x: 0, y: 0 });
  const lastTapAtRef = useRef(0);
  const lastHiddenAtRef = useRef(0);

  const cancelLongPress = () => {
    if (longPressTimerRef.current !== null) {
      window.clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  };

  // A pending long press must not fire after the reader unmounts
  useEffect(() => () => {
    if (longPressTimerRef.current !== null) window.clearTimeout(longPressTimerRef.current);
  }, []);

  // A tap at `x` px from the left of a `width` px reader. Takes the press recorded by the last pointer down.
  const tapAt = (x: number, width: number, target: EventTarget) => {
    const pointerType = pointerTypeRef.current;
    const longPressFired = longPressFiredRef.current;
    pointerTypeRef.current = null;
    longPressFiredRef.current = false;

    const now = Date.now();
    const action = decideTap({
      pointerType,
      longPressFired,
      selectionCollapsed: window.getSelection()?.isCollapsed ?? true,
      onControl: (target as Element).closest(CONTROL_SELECTOR) !== null,
      panelOpen,
      controlsVisible,
      x,
      width,
      leftEdge: settings.leftEdgeTapBehavior,
      rightEdge: settings.rightEdgeTapBehavior,
      singleTap: settings.centerSingleTap,
      doubleTap: settings.centerDoubleTap,
      now,
      lastTapAt: lastTapAtRef.current,
      lastHiddenAt: lastHiddenAtRef.current,
      seekTap: () => seekTap(target as Node),
    });

    switch (action) {
      case 'closePanel':
        closePanel();
        break;
      case 'hideControls':
        setControlsVisible(false);
        lastHiddenAtRef.current = now;
        break;
      case 'edgeLeft':
        onEdge('left', settings.leftEdgeTapBehavior);
        break;
      case 'edgeRight':
        onEdge('right', settings.rightEdgeTapBehavior);
        break;
      case 'showControls':
        setControlsVisible(true);
        break;
      case 'fullscreen':
        // The first tap may have shown the controls; the reader goes clean
        setControlsVisible(false);
        onFullscreen();
        break;
      default:
        // 'ignore' and 'seek' have nothing left to do
        break;
    }
    // The next tap pairs with this one; a completed double tap does not start another
    if (pointerType !== null && pointerType !== 'mouse' && action !== 'closePanel' && action !== 'ignore') {
      lastTapAtRef.current = action === 'fullscreen' ? 0 : now;
    }
  };

  const onClick = (e: ReactMouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    tapAt(e.clientX - rect.left, e.currentTarget.clientWidth, e.target);
  };

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    pointerTypeRef.current = e.pointerType;
    longPressFiredRef.current = false;
    cancelLongPress();
    if (settings.centerLongPress === 'none' || e.pointerType === 'mouse' || controlsVisible || panelOpen) return;

    pressStartRef.current = { x: e.clientX, y: e.clientY };
    longPressTimerRef.current = window.setTimeout(() => {
      longPressTimerRef.current = null;
      longPressFiredRef.current = true;
      if (settings.centerLongPress === 'controls') setControlsVisible(true);
      else onFullscreen();
    }, LONG_PRESS_MS);
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (longPressTimerRef.current === null) return;
    const dx = e.clientX - pressStartRef.current.x;
    const dy = e.clientY - pressStartRef.current.y;
    if (Math.hypot(dx, dy) > LONG_PRESS_MOVE_PX) cancelLongPress();
  };

  const onPointerCancel = () => {
    cancelLongPress();
    pointerTypeRef.current = null;
  };

  // Long press can open the system menu, which would hide the bars again
  const onContextMenu = (e: ReactMouseEvent<HTMLDivElement>) => {
    if (settings.centerLongPress !== 'none') e.preventDefault();
  };

  return {
    tapProps: {
      onClick,
      onPointerDown,
      onPointerMove,
      onPointerUp: cancelLongPress,
      onPointerCancel,
      onContextMenu,
    },
    tapAt,
  };
}
