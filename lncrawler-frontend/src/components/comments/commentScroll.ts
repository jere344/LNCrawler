// The bottom edge of the site header while it covers the top of the window; 0 when it scrolls away with the page
const siteHeaderBottom = (): number => {
  const header = document.querySelector<HTMLElement>('[data-app-header]');
  if (!header || !['fixed', 'sticky'].includes(getComputedStyle(header).position)) return 0;
  return Math.max(0, header.getBoundingClientRect().bottom);
};

// The scroll position of the comments: the element they scroll in, or the page when they have none
export const readScroll = (scroller: HTMLElement | null): number =>
  scroller ? scroller.scrollTop : window.scrollY;

export const writeScroll = (scroller: HTMLElement | null, top: number): void => {
  if (scroller) scroller.scrollTop = top;
  else window.scrollTo({ top });
};

// The scroll position where the comments start: the top of their element, or the top of their section on the page, below the site header
export const commentsTop = (scroller: HTMLElement | null, anchor: HTMLElement | null): number => {
  if (scroller) return 0;
  return anchor ? window.scrollY + anchor.getBoundingClientRect().top - siteHeaderBottom() : window.scrollY;
};

// Scrolls so that `target` sits `margin` px under the top of the comments' visible area, which starts under the site header on the page
export const scrollToComment = (scroller: HTMLElement | null, target: HTMLElement, margin: number): void => {
  const visibleTop = scroller ? scroller.getBoundingClientRect().top : siteHeaderBottom();
  writeScroll(scroller, readScroll(scroller) + target.getBoundingClientRect().top - visibleTop - margin);
};
