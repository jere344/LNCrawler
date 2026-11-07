import type { TFunction } from 'i18next';

const pad = (value: number) => String(value).padStart(2, '0');

/** "m:ss" under an hour, "h:mm:ss" from an hour on. Negative or unknown values read as 0:00. */
export function formatClock(seconds: number): string {
  const total = Number.isFinite(seconds) && seconds > 0 ? Math.floor(seconds) : 0;
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(secs)}` : `${minutes}:${pad(secs)}`;
}

/** Localized total, "12 h 30 min" or "45 min". */
export function formatHours(seconds: number, t: TFunction): string {
  const total = Number.isFinite(seconds) && seconds > 0 ? Math.floor(seconds / 60) : 0;
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  return hours > 0
    ? t('audioPlayer.durationHoursMinutes', { hours, minutes })
    : t('audioPlayer.durationMinutes', { count: minutes });
}
