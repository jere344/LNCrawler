import { describe, expect, it, vi } from 'vitest';
import type { Comment, CommentOrdering } from '@models/comments_types';
import { createCommentsCache, type CommentTarget } from './commentsCache';

const comment = (id: string, extra: Partial<Comment> = {}): Comment => ({
  id,
  author_name: `author-${id}`,
  message: `message ${id}`,
  contains_spoiler: false,
  created_at: '2026-01-01T00:00:00Z',
  upvotes: 0,
  downvotes: 0,
  vote_score: 0,
  user: { id: '', username: '', profile_pic: '' },
  edited: false,
  ...extra,
});

// Two root comments in each ordering
const comments = (ordering: CommentOrdering): Comment[] => [
  comment(`${ordering}-a`),
  comment(`${ordering}-b`),
];

const chapter = (sourceSlug = 'site'): CommentTarget => ({ kind: 'chapter', novelSlug: 'rising', sourceSlug, chapterNumber: 12 });
const novel = (): CommentTarget => ({ kind: 'novel', novelSlug: 'rising' });

const setup = () => {
  const fetchComments = vi.fn(async (_target: CommentTarget, ordering: CommentOrdering) => comments(ordering));
  return { cache: createCommentsCache(fetchComments), fetchComments };
};

const ids = (roots: Comment[]) => roots.map((root) => root.id);

describe('commentsCache', () => {
  it('loads the comments once for concurrent callers and shares the result', async () => {
    const { cache, fetchComments } = setup();
    const [a, b] = await Promise.all([
      cache.load(chapter(), 'new'),
      cache.load(chapter(), 'new'),
    ]);
    expect(a).toBe(b);
    expect(fetchComments).toHaveBeenCalledTimes(1);
    expect(ids(a.roots)).toEqual(['new-a', 'new-b']);
  });

  it('answers a loaded chapter without a request', async () => {
    const { cache, fetchComments } = setup();
    await cache.load(chapter(), 'new');
    await cache.load(chapter(), 'new');
    expect(fetchComments).toHaveBeenCalledTimes(1);
  });

  it('peek is empty until the chapter is loaded and never sends a request', () => {
    const { cache, fetchComments } = setup();
    expect(cache.peek(chapter(), 'new')).toBeUndefined();
    expect(fetchComments).not.toHaveBeenCalled();
  });

  it('two sources of the same chapter share one entry', async () => {
    const { cache, fetchComments } = setup();
    await cache.load(chapter('site-a'), 'new');
    const fromOtherSource = await cache.load(chapter('site-b'), 'new');
    expect(fetchComments).toHaveBeenCalledTimes(1);
    expect(fetchComments.mock.calls[0][0]).toEqual(chapter('site-a'));
    expect(cache.peek(chapter('site-b'), 'new')).toBe(fromOtherSource);
  });

  it('keeps each ordering in its own entry', async () => {
    const { cache, fetchComments } = setup();
    const top = await cache.load(chapter(), 'top');
    const fresh = await cache.load(chapter(), 'new');
    expect(fetchComments).toHaveBeenCalledTimes(2);
    expect(ids(top.roots)).toEqual(['top-a', 'top-b']);
    expect(ids(fresh.roots)).toEqual(['new-a', 'new-b']);
    expect(fetchComments.mock.calls[1][1]).toBe('new');
  });

  it('does not keep a failed request', async () => {
    const fetchComments = vi.fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockImplementation(async (_target: CommentTarget, ordering: CommentOrdering) => comments(ordering));
    const cache = createCommentsCache(fetchComments);
    await expect(cache.load(chapter(), 'new')).rejects.toThrow('offline');
    expect(cache.peek(chapter(), 'new')).toBeUndefined();
    await cache.load(chapter(), 'new');
    expect(fetchComments).toHaveBeenCalledTimes(2);
  });

  it('addRoot prepends the comment in every loaded ordering', async () => {
    const { cache } = setup();
    await cache.load(chapter(), 'top');
    await cache.load(chapter(), 'new');
    cache.addRoot(chapter(), comment('mine'));

    for (const ordering of ['top', 'new'] as const) {
      expect(ids(cache.peek(chapter(), ordering)?.roots ?? [])[0]).toBe('mine');
    }
  });

  it('addRoot does not add a comment twice', async () => {
    const { cache } = setup();
    await cache.load(chapter(), 'new');
    cache.addRoot(chapter(), comment('mine'));
    cache.addRoot(chapter(), comment('mine'));
    expect(cache.peek(chapter(), 'new')?.roots).toHaveLength(3);
  });

  it('addRoot leaves an ordering that is not loaded alone', async () => {
    const { cache } = setup();
    await cache.load(chapter(), 'new');
    cache.addRoot(chapter(), comment('mine'));
    expect(cache.peek(chapter(), 'top')).toBeUndefined();
  });

  it('addReply inserts the reply under its parent in every loaded ordering', async () => {
    const { cache } = setup();
    await cache.load(chapter(), 'top');
    await cache.load(chapter(), 'new');
    cache.addReply(chapter(), 'new-a', comment('reply'));
    cache.addReply(chapter(), 'top-a', comment('reply'));

    expect(cache.peek(chapter(), 'new')?.roots[0].replies?.map((r) => r.id)).toEqual(['reply']);
    expect(cache.peek(chapter(), 'top')?.roots[0].replies?.map((r) => r.id)).toEqual(['reply']);
    expect(cache.peek(chapter(), 'new')?.roots).toHaveLength(2);
  });

  it('replace updates the comment in every loaded ordering and keeps its replies', async () => {
    const { cache } = setup();
    await cache.load(chapter(), 'top');
    await cache.load(chapter(), 'new');
    cache.addReply(chapter(), 'new-a', comment('reply'));
    cache.replace(chapter(), comment('new-a', { message: 'edited', vote_score: 3 }));
    cache.replace(chapter(), comment('top-b', { message: 'edited', vote_score: 1 }));

    const fresh = cache.peek(chapter(), 'new')?.roots[0];
    expect(fresh?.message).toBe('edited');
    expect(fresh?.replies?.map((r) => r.id)).toEqual(['reply']);
    expect(cache.peek(chapter(), 'top')?.roots[1].message).toBe('edited');
  });

  it('sends the novel target to the fetcher, with its own entries', async () => {
    const { cache, fetchComments } = setup();
    await cache.load(novel(), 'top');
    expect(fetchComments.mock.calls[0][0]).toEqual({ kind: 'novel', novelSlug: 'rising' });
    expect(ids(cache.peek(novel(), 'top')?.roots ?? [])).toEqual(['top-a', 'top-b']);
    expect(cache.peek(novel(), 'new')).toBeUndefined();
  });

  it('keeps a novel apart from a chapter of the same novel', async () => {
    const { cache, fetchComments } = setup();
    await cache.load(novel(), 'new');
    await cache.load(chapter(), 'new');
    expect(fetchComments).toHaveBeenCalledTimes(2);
    expect(cache.peek(novel(), 'new')).not.toBe(cache.peek(chapter(), 'new'));
  });

  it('addRoot and addReply reach a loaded novel, not its chapters', async () => {
    const { cache } = setup();
    await cache.load(novel(), 'new');
    await cache.load(chapter(), 'new');
    cache.addRoot(novel(), comment('mine'));
    cache.addReply(novel(), 'new-a', comment('reply'));

    expect(ids(cache.peek(novel(), 'new')?.roots ?? [])[0]).toBe('mine');
    expect(cache.peek(novel(), 'new')?.roots[1].replies?.map((r) => r.id)).toEqual(['reply']);
    expect(ids(cache.peek(chapter(), 'new')?.roots ?? [])).toEqual(['new-a', 'new-b']);
  });

  it('replace updates a novel comment in the loaded orderings that hold it', async () => {
    const { cache } = setup();
    await cache.load(novel(), 'top');
    await cache.load(novel(), 'new');
    cache.replace(novel(), comment('top-b', { message: 'edited' }));

    expect(cache.peek(novel(), 'top')?.roots[1].message).toBe('edited');
    expect(cache.peek(novel(), 'new')?.roots.some((root) => root.message === 'edited')).toBe(false);
  });
});
