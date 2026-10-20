import type { TFunction } from 'i18next';
import type { ApiError } from '@services/api';

// Error text returned by the API as { "error": "..." }, if any.
export const apiErrorMessage = (err: unknown): string | undefined => {
  const data = (err as ApiError | undefined)?.response?.data;
  return typeof data?.error === 'string' ? data.error : undefined;
};

// The server's message when it sent one, otherwise the translated fallback.
export const getApiErrorMessage = (err: unknown, t: TFunction, fallbackKey: string): string =>
  apiErrorMessage(err) || t(fallbackKey);
