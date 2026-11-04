import { useEffect, useRef, type HTMLAttributes, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent } from 'react';
import type { ControlsTrigger, EdgeTapBehavior, ReaderSettings } from '../readerSettingsSchema';

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
  trigger: ControlsTrigger;
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
  if (input.controlsVisible) return 'hideControls';

  // An edge set to 'none' falls through to the centre behaviour
  const edgeWidth = input.width * (EDGE_TAP_WIDTH_PERCENTAGE / 100);
  if (input.x <= edgeWidth && input.leftEdge !== 'none') return 'edgeLeft';
  if (input.x >= input.width - edgeWidth && input.rightEdge !== 'none') return 'edgeRight';

  if (input.seekTap()) return 'seek';

  if (input.trigger === 'singleTap') return 'showControls';
  if (input.trigger === 'doubleTap') {
    // The tap that hid the controls must not count as the first of a double tap
    const isDoubleTap = input.now - input.lastTapAt < DOUBLE_TAP_MS && input.now - input.lastHiddenAt > DOUBLE_TAP_MS;
    return isDoubleTap ? 'showControls' : 'recordTap';
  }
  return 'ignore';
}

interface TapOptions {
  settings: Pick<ReaderSettings, 'controlsTrigger' | 'leftEdgeTapBehavior' | 'rightEdgeTapBehavior'>;
  controlsVisible: boolean;
  panelOpen: boolean;
  setControlsVisible: (visible: boolean) => void;
  closePanel: () => void;
  onEdge: (edge: 'left' | 'right', behavior: EdgeTapBehavior) => void;
  seekTap: (target: Node) => boolean;
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
      trigger: settings.controlsTrigger,
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
      case 'recordTap':
        lastTapAtRef.current = now;
        break;
      default:
        // 'ignore' and 'seek' have nothing left to do
        break;
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
    if (settings.controlsTrigger !== 'longPress' || e.pointerType === 'mouse' || controlsVisible || panelOpen) return;

    pressStartRef.current = { x: e.clientX, y: e.clientY };
    longPressTimerRef.current = window.setTimeout(() => {
      longPressTimerRef.current = null;
      longPressFiredRef.current = true;
      setControlsVisible(true);
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
    if (settings.controlsTrigger === 'longPress') e.preventDefault();
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
