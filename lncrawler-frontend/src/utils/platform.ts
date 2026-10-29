/** iPhone, iPad, iPod, and macOS Safari. iPadOS reports itself as a Mac, told apart by touch support. */
export function isApplePlatform(): boolean {
  if (typeof navigator === 'undefined') return false;
  const { userAgent, maxTouchPoints } = navigator;
  if (/iPhone|iPad|iPod/.test(userAgent)) return true;
  if (/Macintosh/.test(userAgent) && maxTouchPoints > 1) return true;
  return /Macintosh/.test(userAgent) && /Safari/.test(userAgent) && !/Chrome|Chromium|Edg|OPR/.test(userAgent);
}
