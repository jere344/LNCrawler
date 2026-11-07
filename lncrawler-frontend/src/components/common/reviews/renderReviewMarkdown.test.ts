import { describe, it, expect } from 'vitest';
import { renderReviewMarkdown } from './renderReviewMarkdown';

const render = (markdown: string): HTMLDivElement => {
  const container = document.createElement('div');
  container.innerHTML = renderReviewMarkdown(markdown);
  return container;
};

describe('renderReviewMarkdown', () => {
  it('renders bold, italic and underline', () => {
    const el = render('**bold** *italic* <u>under</u>');
    expect(el.querySelector('strong')?.textContent).toBe('bold');
    expect(el.querySelector('em')?.textContent).toBe('italic');
    expect(el.querySelector('u')?.textContent).toBe('under');
  });

  it('renders lists', () => {
    const el = render('- one\n- two');
    expect(el.querySelector('ul > li')?.textContent).toBe('one');
    expect(el.querySelectorAll('li')).toHaveLength(2);
  });

  it('renders blockquotes', () => {
    const el = render('> quoted text');
    expect(el.querySelector('blockquote')?.textContent).toContain('quoted text');
  });

  it('renders headings', () => {
    const el = render('# Title\n\n### Sub');
    expect(el.querySelector('h1')?.textContent).toBe('Title');
    expect(el.querySelector('h3')?.textContent).toBe('Sub');
  });

  it('strips script tags and their content', () => {
    const html = renderReviewMarkdown('before <script>alert(1)</script> after');
    expect(html).not.toContain('<script');
    expect(html).not.toContain('alert');
    expect(html).toContain('before');
  });

  it('strips event handler attributes', () => {
    const el = render('<span onclick="alert(1)">hi</span>');
    expect(el.innerHTML).not.toContain('onclick');
    expect(el.textContent).toContain('hi');
  });

  it('strips javascript: hrefs', () => {
    const el = render('[click](javascript:alert(1))');
    const link = el.querySelector('a');
    expect(link?.getAttribute('href')).toBeNull();
    expect(el.innerHTML).not.toContain('javascript:');
  });

  it('strips images and onerror handlers', () => {
    const el = render('<img src="x" onerror="alert(1)">\n\n![alt](https://example.com/a.png)');
    expect(el.querySelector('img')).toBeNull();
    expect(el.innerHTML).not.toContain('onerror');
  });

  it('forces rel and target on links', () => {
    const el = render('[site](https://example.com)');
    const link = el.querySelector('a');
    expect(link?.getAttribute('href')).toBe('https://example.com');
    expect(link?.getAttribute('target')).toBe('_blank');
    expect(link?.getAttribute('rel')).toBe('noopener noreferrer nofollow');
  });
});
