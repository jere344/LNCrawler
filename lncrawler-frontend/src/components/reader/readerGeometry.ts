// The dim band is a percentage of the screen width. It tops out at about 200px, so it stays an edge on large screens.
const DIM_BAND_MAX_PX = 200;
const DIM_BAND_LIMIT = 30;
const DIM_BAND_STEP = 5;

// The widest band allowed on a screen of this width, in percent, in steps of 5
export const dimBandMax = (viewportWidth: number): number =>
  Math.min(DIM_BAND_LIMIT, Math.floor((DIM_BAND_MAX_PX / viewportWidth) * 100 / DIM_BAND_STEP) * DIM_BAND_STEP);

// The band width in use: the saved width, held to the screen's limit. The saved width itself is kept.
export const dimBandWidth = (saved: number, viewportWidth: number): number =>
  Math.min(saved, dimBandMax(viewportWidth));

// A drag of this many px, top to bottom, sweeps the dim level across its whole range
const DIM_DRAG_PX = 240;
export const DIM_LEVEL_MAX = 90;
const DIM_LEVEL_STEP = 5;

// The dim level after a drag of `dy` px from `start` (downward is darker), in steps of 5
export const dimLevelFromDrag = (start: number, dy: number): number => {
  const level = Math.round((start + (dy / DIM_DRAG_PX) * DIM_LEVEL_MAX) / DIM_LEVEL_STEP) * DIM_LEVEL_STEP;
  return Math.min(DIM_LEVEL_MAX, Math.max(0, level));
};
