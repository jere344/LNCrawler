import { describe, expect, it } from 'vitest';
import { classifyChapterError } from './chapterErrors';

const info = { chapter_id: 7, title: 'Seven', novel_title: 'Novel', prev_chapter: 6, next_chapter: 8 };

describe('classifyChapterError', () => {
  it('reports a 451 as a DMCA removal', () => {
    expect(classifyChapterError({ response: { status: 451 } })).toEqual({ kind: 'dmca' });
  });

  it('reports a 404 with a chapter payload as unavailable', () => {
    expect(classifyChapterError({ response: { status: 404, data: info } }))
      .toEqual({ kind: 'unavailable', info });
  });

  it('reports anything else as a generic error', () => {
    expect(classifyChapterError({ response: { status: 404, data: { detail: 'not found' } } })).toEqual({ kind: 'error' });
    expect(classifyChapterError({ response: { status: 500 } })).toEqual({ kind: 'error' });
  });

  it('reports a non-object error as a generic error', () => {
    expect(classifyChapterError(null)).toEqual({ kind: 'error' });
    expect(classifyChapterError('network down')).toEqual({ kind: 'error' });
  });
});
