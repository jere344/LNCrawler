const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8185';

// Errors already sent this session, so a render/loop that throws on every
// frame does not flood the backend.
const reported = new Set<string>();

export interface ErrorContext {
  url?: string;
  context?: string;
}

/**
 * Report an unexpected error to the backend, which opens a GitHub issue.
 * Expected client errors (HTTP 4xx) are ignored, and reporting never throws.
 */
export const reportError = (error: unknown, ctx: ErrorContext = {}): void => {
  try {
    const err = error instanceof Error ? error : new Error(String(error));

    const status = (err as { response?: { status?: number } }).response?.status;
    if (status !== undefined && status >= 400 && status < 500) return;

    const key = err.message || 'unknown';
    if (reported.has(key)) return;
    reported.add(key);

    void fetch(`${API_BASE_URL}/report-error/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      keepalive: true,
      body: JSON.stringify({
        message: err.message || 'Unknown error',
        stack: err.stack || '',
        url: ctx.url || window.location.href,
        context: ctx.context || '',
      }),
    }).catch(() => {});
  } catch {
    // never let error reporting break the app
  }
};
