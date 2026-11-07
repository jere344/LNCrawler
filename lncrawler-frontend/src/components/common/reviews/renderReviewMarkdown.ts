import { marked } from 'marked';
import DOMPurify from 'dompurify';

// Dedicated instance: the global DOMPurify (reader, synopsis) keeps its own config and hooks.
const purify = DOMPurify(window);

purify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank');
    node.setAttribute('rel', 'noopener noreferrer nofollow');
  }
});

export const renderReviewMarkdown = (markdown: string): string => {
  const html = marked.parse(markdown, { gfm: true, breaks: false, async: false });

  return purify.sanitize(html, {
    ALLOWED_TAGS: [
      'p', 'br', 'strong', 'em', 'u', 'del',
      'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'ul', 'ol', 'li', 'blockquote', 'hr',
      'a', 'code', 'pre',
    ],
    ALLOWED_ATTR: ['href'],
    ALLOW_DATA_ATTR: false,
  });
};
