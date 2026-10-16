/**
 * Turns the rendered chapter (#reader-content) into speakable chunks, and
 * maps chunks back to the DOM for highlighting and auto-scroll.
 *
 * Blocks are always re-queried from the live DOM by index, because the
 * reader may re-render its HTML (e.g. after a font change).
 */

const BLOCK_SELECTOR = 'p, h1, h2, h3, h4, h5, h6, li, blockquote, pre, td, th, dt, dd, figcaption';
const SKIP_TAGS = new Set(['STYLE', 'SCRIPT', 'NOSCRIPT', 'RT', 'RP', 'TEMPLATE']);

/** Longest chunk handed to a voice; sentences above this are split further. */
const MAX_CHUNK = 280;
/** Dense scripts pack more speech per character (Supertonic caps ja/ko at 120). */
const MAX_CHUNK_CJK = 120;
const CJK_LANGS = new Set(['ja', 'ko', 'zh', 'th']);
/** Short consecutive sentences are merged until they reach this length. */
const MIN_CHUNK = 60;

export interface TtsChunk {
  /** Index of the block element, or -1 for the virtual title chunk. */
  block: number;
  /** Character offsets inside the block's text. */
  start: number;
  end: number;
  text: string;
}

export interface TtsDocument {
  chunks: TtsChunk[];
  blockCount: number;
  /** First chunk index of each block (−1 if the block has nothing to read). */
  blockFirstChunk: number[];
}

export const getContentRoot = (): HTMLElement | null => document.getElementById('reader-content');

/** Readable block elements, innermost only (a <blockquote><p> yields the <p>). */
export function getBlocks(root: HTMLElement): HTMLElement[] {
  const all = Array.from(root.querySelectorAll<HTMLElement>(BLOCK_SELECTOR));
  const blocks = all.filter(el => !el.querySelector(BLOCK_SELECTOR));
  return blocks.length ? blocks : [root];
}

function textNodes(el: HTMLElement): Text[] {
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
    acceptNode: node => {
      for (let p = node.parentElement; p && p !== el; p = p.parentElement) {
        if (SKIP_TAGS.has(p.tagName)) return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const nodes: Text[] = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) nodes.push(n as Text);
  return nodes;
}

const blockText = (el: HTMLElement) => textNodes(el).map(n => n.data).join('');

// "[TL: ...]", "(T/N ...)", "[Editor's note: ...]" and similar asides.
const INLINE_NOTE = /[([【（](?:\s*(?:T\/?N|TL|TLN|ED|E\/N|PR|Translator'?s?\s*note|Editor'?s?\s*note|Note))\s*[:：.\-–]?[^)\]】）]*[)\]】）]/gi;
// Paragraphs that are entirely a note.
const NOTE_PARAGRAPH = /^\s*(?:T\/?N|TL\s*(?:note|N)?|Translator'?s?\s*notes?|Editor'?s?\s*notes?|PR|E\/N)\s*[:：]/i;
// Separators such as "***", "———", "◇◇◇", "~~~".
const ONLY_SYMBOLS = /^[\s\p{P}\p{S}]*$/u;
const URL_PATTERN = /\bhttps?:\/\/\S+/gi;

/** Blank out (same length, so offsets stay valid) text that shouldn't be read. */
function maskUnreadable(text: string, skipNotes: boolean): string {
  const blank = (m: string) => ' '.repeat(m.length);
  let out = text.replace(URL_PATTERN, blank);
  if (skipNotes) out = out.replace(INLINE_NOTE, blank);
  // Long runs of the same symbol ("!!!!!!", "......") are read out literally
  // by some voices.
  out = out.replace(/([^\p{L}\p{N}\s])\1{3,}/gu, (m, c: string) => c + ' '.repeat(m.length - 1));
  return out;
}

interface Span { start: number; end: number }

function sentenceSpans(text: string, lang: string): Span[] {
  const spans: Span[] = [];
  type SegmenterCtor = new (lang: string, opts: { granularity: 'sentence' }) => {
    segment: (input: string) => Iterable<{ index: number; segment: string }>;
  };
  const Segmenter = (Intl as unknown as { Segmenter?: SegmenterCtor }).Segmenter;
  if (Segmenter) {
    for (const s of new Segmenter(lang, { granularity: 'sentence' }).segment(text)) {
      spans.push({ start: s.index, end: s.index + s.segment.length });
    }
  } else {
    const re = /[^.!?。！？…]+[.!?。！？…]*["'”’」』)\]]*\s*/g;
    for (let m = re.exec(text); m; m = re.exec(text)) {
      spans.push({ start: m.index, end: m.index + m[0].length });
    }
    if (!spans.length) spans.push({ start: 0, end: text.length });
  }
  return spans;
}

/** Split a long span at the last comma/space before `max`. */
function splitLong(text: string, span: Span, max: number): Span[] {
  const out: Span[] = [];
  let start = span.start;
  while (span.end - start > max) {
    const window = text.slice(start, start + max);
    let cut = Math.max(
      window.lastIndexOf(', '), window.lastIndexOf('; '), window.lastIndexOf('，'),
      window.lastIndexOf('、'), window.lastIndexOf(' — '),
    );
    if (cut < max / 3) cut = window.lastIndexOf(' ');
    if (cut < max / 3) cut = max - 1;
    out.push({ start, end: start + cut + 1 });
    start += cut + 1;
  }
  out.push({ start, end: span.end });
  return out;
}

export interface BuildOptions {
  lang: string;
  skipNotes: boolean;
  title?: string;
}

export function buildDocument(root: HTMLElement, opts: BuildOptions): TtsDocument {
  const blocks = getBlocks(root);
  const chunks: TtsChunk[] = [];
  const blockFirstChunk: number[] = [];
  const maxChunk = CJK_LANGS.has(opts.lang) ? MAX_CHUNK_CJK : MAX_CHUNK;

  if (opts.title?.trim()) {
    chunks.push({ block: -1, start: 0, end: 0, text: opts.title.trim() });
  }

  blocks.forEach((el, blockIndex) => {
    blockFirstChunk.push(-1);
    const raw = blockText(el);
    if (ONLY_SYMBOLS.test(raw)) return;
    if (opts.skipNotes && NOTE_PARAGRAPH.test(raw)) return;
    const text = maskUnreadable(raw, opts.skipNotes);

    const spans = sentenceSpans(text, opts.lang).flatMap(s => splitLong(text, s, maxChunk));
    let pending: Span | null = null;
    const flush = () => {
      if (!pending) return;
      const spoken = text.slice(pending.start, pending.end).replace(/\s+/g, ' ').trim();
      if (spoken && !ONLY_SYMBOLS.test(spoken)) {
        if (blockFirstChunk[blockIndex] === -1) blockFirstChunk[blockIndex] = chunks.length;
        chunks.push({ block: blockIndex, start: pending.start, end: pending.end, text: spoken });
      }
      pending = null;
    };
    for (const span of spans) {
      if (pending && span.end - pending.start <= maxChunk && pending.end - pending.start < MIN_CHUNK) {
        pending = { start: pending.start, end: span.end };
      } else {
        flush();
        pending = { ...span };
      }
    }
    flush();
  });

  return { chunks, blockCount: blocks.length, blockFirstChunk };
}

/** DOM Range covering [start, end) of a block's text. */
export function rangeFor(el: HTMLElement, start: number, end: number): Range | null {
  const nodes = textNodes(el);
  const range = document.createRange();
  let offset = 0;
  let startSet = false;
  for (const node of nodes) {
    const len = node.data.length;
    if (!startSet && start < offset + len) {
      range.setStart(node, start - offset);
      startSet = true;
    }
    if (startSet && end <= offset + len) {
      range.setEnd(node, end - offset);
      return range;
    }
    offset += len;
  }
  if (!startSet) return null;
  const last = nodes[nodes.length - 1];
  range.setEnd(last, last.data.length);
  return range;
}

/** Index of the block containing `target`, or -1. */
export function blockIndexOf(root: HTMLElement, target: Node): number {
  const blocks = getBlocks(root);
  for (let el: Node | null = target; el && el !== root.parentNode; el = el.parentNode) {
    const i = blocks.indexOf(el as HTMLElement);
    if (i !== -1) return i;
  }
  return -1;
}

/** First block whose bottom is below `topOffset` px from the viewport top. */
export function firstVisibleBlock(root: HTMLElement, topOffset: number): number {
  const blocks = getBlocks(root);
  const i = blocks.findIndex(el => el.getBoundingClientRect().bottom > topOffset);
  return Math.max(0, i);
}

// ---------------------------------------------------------------------------
// Highlighting
// ---------------------------------------------------------------------------

const ACTIVE_CLASS = 'tts-active-block';
const HIGHLIGHT_NAME = 'tts-sentence';
const STYLE_ID = 'tts-highlight-style';

type HighlightRegistry = { set: (name: string, h: unknown) => void; delete: (name: string) => void };
const highlightRegistry = (): HighlightRegistry | null =>
  (typeof CSS !== 'undefined' && (CSS as unknown as { highlights?: HighlightRegistry }).highlights) || null;
const HighlightCtor = (): (new (...ranges: Range[]) => unknown) | null =>
  (window as unknown as { Highlight?: new (...ranges: Range[]) => unknown }).Highlight ?? null;

export const supportsSentenceHighlight = () => !!highlightRegistry() && !!HighlightCtor();

/** Inject the highlight styles; colors come from the MUI theme. */
export function ensureHighlightStyle(blockColor: string, sentenceColor: string): void {
  let style = document.getElementById(STYLE_ID) as HTMLStyleElement | null;
  if (!style) {
    style = document.createElement('style');
    style.id = STYLE_ID;
    document.head.appendChild(style);
  }
  style.textContent = `
    #reader-content .${ACTIVE_CLASS} {
      background-color: ${blockColor};
      box-shadow: 0 0 0 0.35em ${blockColor};
      border-radius: 2px;
      transition: background-color 0.2s;
    }
    ::highlight(${HIGHLIGHT_NAME}) { background-color: ${sentenceColor}; }
  `;
}

export function clearHighlight(): void {
  document.querySelectorAll(`.${ACTIVE_CLASS}`).forEach(el => el.classList.remove(ACTIVE_CLASS));
  highlightRegistry()?.delete(HIGHLIGHT_NAME);
}

export type HighlightMode = 'none' | 'paragraph' | 'sentence';

/** Highlight a chunk and return the element/range to scroll to. */
export function highlightChunk(
  root: HTMLElement,
  chunk: TtsChunk,
  mode: HighlightMode,
): { el: HTMLElement; range: Range | null } | null {
  clearHighlight();
  if (chunk.block < 0) return null;
  const el = getBlocks(root)[chunk.block];
  if (!el) return null;
  const range = rangeFor(el, chunk.start, chunk.end);
  if (mode === 'paragraph' || (mode === 'sentence' && !supportsSentenceHighlight())) {
    el.classList.add(ACTIVE_CLASS);
  } else if (mode === 'sentence' && range) {
    const Ctor = HighlightCtor()!;
    highlightRegistry()!.set(HIGHLIGHT_NAME, new Ctor(range));
  }
  return { el, range };
}
