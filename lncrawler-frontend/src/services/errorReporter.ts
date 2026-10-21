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
  /__firefox__/i,
  /^Script error\.?$/,
  /dynamically imported module/i,
  /Importing a module script failed/i,
  /Unable to preload CSS/i,
  /^Failed to fetch$/,
  /NetworkError when attempting to fetch resource/i,
  /Firefox can't establish a connection/i,
  /^Load failed$/,
  /ResizeObserver loop/i,
  // DOM-node NotFoundError raised while React unmounts nodes the browser
  // (translation/reader extensions) already removed or moved. Same bug on
  // unmount (removeChild) and on insert (insertBefore), two browsers.
  /The node to be removed is not a child of this node/i,
  /The node before which the new node is to be inserted is not a child of this node/i,
  /The object can not be found here/i,
];

const isIgnorable = (message: string): boolean =>
  IGNORABLE_PATTERNS.some((re) => re.test(message));

// Browser extensions inject handlers into the page, so their rejected promises
// surface through our window listeners. The message is generic ("Cannot read
// properties of undefined..."), but the top stack frame names the extension
// scheme, which is the reliable signal. Not ours to fix.
const EXTENSION_ORIGIN = /(?:chrome|moz|safari|ms-browser)(?:-web)?-extension:\/\//i;

// Our code is always served from a hashed `/assets/*.js` bundle; a script with
// frames attributed to the document itself was injected into the page (Firefox
// reader/quality extensions, edge proxies such as Rocket Loader). Those can
// recurse or throw on our pages without a line existing in this repo.
const ASSET_PATH = '/assets/';
const isInjectedScript = (stack: string): boolean => {
  const first = stack.split('\n').find((line) => line.trim()) ?? '';
  const url = first.match(/https?:\/\/[^\s)]+/)?.[0] ?? '';
  return url.includes('://') && !url.includes(ASSET_PATH);
};

const topFrame = (stack: string): string =>
  stack.split('\n').find((line) => line.trim().startsWith('at ')) ?? '';

const isExtensionError = (stack: string): boolean =>
  EXTENSION_ORIGIN.test(topFrame(stack)) || isInjectedScript(stack);

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
    // A cross-realm Error (extension/iframe) is not `instanceof Error` here, so
    // `err.stack` would point at this reporter. Keep the original stack when the
    // reason carries one, so the real origin (e.g. an extension frame) shows up.
    const stack = (error as { stack?: string } | null)?.stack || err.stack || '';

    if (isIgnorable(err.message || '') || isExtensionError(stack)) return;

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
        stack: stack.slice(0, MAX_STACK_LENGTH),
        url: ctx.url || window.location.href,
        context: ctx.context || '',
      }),
    }).catch(() => {});
  } catch {
    // never let error reporting break the app
  }
};
