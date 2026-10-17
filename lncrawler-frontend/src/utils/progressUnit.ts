import type { TFunction } from 'i18next';

const UNIT_KEYS: Record<string, string> = {
  chapters: 'units.chapters',
  images: 'units.imagesCount',
  volumes: 'units.volumes',
};

/** "12 / 80 chapters" with the unit pluralised on the total; empty while the total is unknown. */
export function formatProgress(t: TFunction, progress: number, total: number, unit?: string): string {
  if (!total) return '';
  const key = UNIT_KEYS[unit || 'chapters'];
  return key ? `${progress} / ${t(key, { count: total })}` : `${progress} / ${total} ${unit}`;
}
