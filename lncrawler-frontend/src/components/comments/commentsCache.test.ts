import { describe, expect, it, vi } from 'vitest';
import type { Comment } from '@models/comments_types';
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

// Two root comments, as the server ranks them
const comments = (): Comment[] => [comment('a'), comment('b')];

const chapter = (sourceSlug = 'site'): CommentTarget => ({ kind: 'chapter', novelSlug: 'rising', sourceSlug, chapterNumber: 12 });
const novel = (): CommentTarget => ({ kind: 'novel', novelSlug: 'rising' });

const setup = () => {
  const fetchComments = vi.fn<(target: CommentTarget) => Promise<Comment[]>>(async () => comments());
  return { cache: createCommentsCache(fetchComments), fetchComments };
};

const ids = (roots: Comment[]) => roots.map((root) => root.id);

describe('commentsCache', () => {
  it('loads the comments once for concurrent callers and shares the result', async () => {
    const { cache, fetchComments } = setup();
    const [a, b] = await Promise.all([
      cache.load(chapter()),
      cache.load(chapter()),
    ]);
    expect(a).toBe(b);
    expect(fetchComments).toHaveBeenCalledTimes(1);
    expect(ids(a.roots)).toEqual(['a', 'b']);
  });

  it('answers a loaded chapter without a request', async () => {
    const { cache, fetchComments } = setup();
    await cache.load(chapter());
    await cache.load(chapter());
    expect(fetchComments).toHaveBeenCalledTimes(1);
  });

  it('peek is empty until the chapter is loaded and never sends a request', () => {
    const { cache, fetchComments } = setup();
    expect(cache.peek(chapter())).toBeUndefined();
    expect(fetchComments).not.toHaveBeenCalled();
  });

  it('two sources of the same chapter share one entry', async () => {
    const { cache, fetchComments } = setup();
    await cache.load(chapter('site-a'));
    const fromOtherSource = await cache.load(chapter('site-b'));
    expect(fetchComments).toHaveBeenCalledTimes(1);
    expect(fetchComments.mock.calls[0][0]).toEqual(chapter('site-a'));
    expect(cache.peek(chapter('site-b'))).toBe(fromOtherSource);
  });

  it('does not keep a failed request', async () => {
    const fetchComments = vi.fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockImplementation(async () => comments());
    const cache = createCommentsCache(fetchComments);
    await expect(cache.load(chapter())).rejects.toThrow('offline');
    expect(cache.peek(chapter())).toBeUndefined();
    await cache.load(chapter());
    expect(fetchComments).toHaveBeenCalledTimes(2);
  });

  it('addRoot prepends the comment to the loaded chapter', async () => {
    const { cache } = setup();
    await cache.load(chapter());
    cache.addRoot(chapter(), comment('mine'));

    expect(ids(cache.peek(chapter())?.roots ?? [])[0]).toBe('mine');
  });

  it('addRoot does not add a comment twice', async () => {
    const { cache } = setup();
    await cache.load(chapter());
    cache.addRoot(chapter(), comment('mine'));
    cache.addRoot(chapter(), comment('mine'));
    expect(cache.peek(chapter())?.roots).toHaveLength(3);
  });

  it('addRoot leaves a target that is not loaded alone', () => {
    const { cache, fetchComments } = setup();
    cache.addRoot(chapter(), comment('mine'));
    expect(cache.peek(chapter())).toBeUndefined();
    expect(fetchComments).not.toHaveBeenCalled();
  });

  it('addReply inserts the reply under its parent in the loaded chapter', async () => {
    const { cache } = setup();
    await cache.load(chapter());
    cache.addReply(chapter(), 'a', comment('reply'));

    expect(cache.peek(chapter())?.roots[0].replies?.map((r) => r.id)).toEqual(['reply']);
    expect(cache.peek(chapter())?.roots).toHaveLength(2);
  });

  it('replace updates the comment and keeps its replies', async () => {
    const { cache } = setup();
    await cache.load(chapter());
    cache.addReply(chapter(), 'a', comment('reply'));
    cache.replace(chapter(), comment('a', { message: 'edited', vote_score: 3 }));

    const updated = cache.peek(chapter())?.roots[0];
    expect(updated?.message).toBe('edited');
    expect(updated?.replies?.map((r) => r.id)).toEqual(['reply']);
  });

  it('sends the novel target to the fetcher, with its own entry', async () => {
    const { cache, fetchComments } = setup();
    await cache.load(novel());
    expect(fetchComments.mock.calls[0][0]).toEqual({ kind: 'novel', novelSlug: 'rising' });
    expect(ids(cache.peek(novel())?.roots ?? [])).toEqual(['a', 'b']);
  });

  it('keeps a novel apart from a chapter of the same novel', async () => {
    const { cache, fetchComments } = setup();
    await cache.load(novel());
    await cache.load(chapter());
    expect(fetchComments).toHaveBeenCalledTimes(2);
    expect(cache.peek(novel())).not.toBe(cache.peek(chapter()));
  });

  it('addRoot and addReply reach a loaded novel, not its chapters', async () => {
    const { cache } = setup();
    await cache.load(novel());
    await cache.load(chapter());
    cache.addRoot(novel(), comment('mine'));
    cache.addReply(novel(), 'a', comment('reply'));

    expect(ids(cache.peek(novel())?.roots ?? [])[0]).toBe('mine');
    expect(cache.peek(novel())?.roots[1].replies?.map((r) => r.id)).toEqual(['reply']);
    expect(ids(cache.peek(chapter())?.roots ?? [])).toEqual(['a', 'b']);
  });

  it('replace updates a novel comment', async () => {
    const { cache } = setup();
    await cache.load(novel());
    cache.replace(novel(), comment('b', { message: 'edited' }));

    expect(cache.peek(novel())?.roots[1].message).toBe('edited');
  });
});
