const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8185';

// Errors already sent this session, so a render/loop that throws on every
// frame does not flood the backend.
const reported = new Set<string>();
// Cap the dedup set so a long session can't grow it without bound. Sets keep
// insertion order, so the front entry is the oldest and goes first.
const MAX_REPORTED_KEYS = 100;

// keepalive requests share a browser cap (~64KiB), so keep the stack small.
const MAX_STACK_LENGTH = 16000;

// Not actionable by us: browser-extension injections, cross-origin scripts
// with no usable detail, and transient network/asset failures. Dropping them
// here keeps them out of the GitHub tracker. Mirror of the server-side filter
// in errors_views.py (the server one is authoritative for cached clients).
const IGNORABLE_PATTERNS: RegExp[] = [
  /window\.ethereum/i,
  /^Script error\.?$/,
  /Failed to fetch dynamically imported module/,
  /Unable to preload CSS/,
  /^Failed to fetch$/,
  /NetworkError when attempting to fetch resource/,
  /^Load failed$/,
  /ResizeObserver loop/,
];

const isIgnorable = (message: string): boolean =>
  IGNORABLE_PATTERNS.some((re) => re.test(message));

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

    if (isIgnorable(err.message || '')) return;

    const status = (err as { response?: { status?: number } }).response?.status;
    if (status !== undefined && status >= 400 && status < 500) return;

    // Include where it happened: otherwise every "Request failed with status
    // code 500" collapses into one dedup entry and hides the others.
    const key = `${err.message || 'unknown'}|${ctx.context || ''}|${ctx.url || ''}`;
    if (reported.has(key)) return;
    reported.add(key);
    if (reported.size > MAX_REPORTED_KEYS) {
      const oldest = reported.values().next().value;
      if (oldest !== undefined) reported.delete(oldest);
    }

    void fetch(`${API_BASE_URL}/report-error/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      keepalive: true,
      body: JSON.stringify({
        message: err.message || 'Unknown error',
        stack: (err.stack || '').slice(0, MAX_STACK_LENGTH),
        url: ctx.url || window.location.href,
        context: ctx.context || '',
      }),
    }).catch(() => {});
  } catch {
    // never let error reporting break the app
  }
};
