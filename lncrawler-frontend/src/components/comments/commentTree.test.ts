import { describe, expect, it } from 'vitest';
import type { Comment } from '@models/comments_types';
import { countDescendants, findPath, insertReply, replaceComment } from './commentTree';

const comment = (id: string, replies?: Comment[], extra: Partial<Comment> = {}): Comment => ({
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
  replies,
  ...extra,
});

// a > b > c > d (four levels), plus a sibling root e with no replies
const deepTree = (): Comment[] => [
  comment('a', [comment('b', [comment('c', [comment('d')])])]),
  comment('e'),
];

const ids = (list: Comment[]) => list.map((item) => item.id);

describe('findPath', () => {
  it('gives the chain from the root down to the target', () => {
    expect(ids(findPath(deepTree(), 'd') ?? [])).toEqual(['a', 'b', 'c', 'd']);
  });

  it('gives a single root for a root comment', () => {
    expect(ids(findPath(deepTree(), 'e') ?? [])).toEqual(['e']);
  });

  it('is null when the id is not in the tree', () => {
    expect(findPath(deepTree(), 'missing')).toBeNull();
  });
});

describe('countDescendants', () => {
  it('counts replies at every depth', () => {
    const [a] = deepTree();
    expect(countDescendants(a)).toBe(3);
  });

  it('is 0 for a comment without replies', () => {
    expect(countDescendants(comment('x'))).toBe(0);
    expect(countDescendants(comment('x', []))).toBe(0);
  });
});

describe('insertReply', () => {
  it('prepends the reply to the replies of a root comment, newest first', () => {
    const roots = [comment('a', [comment('a1')])];
    const result = insertReply(roots, 'a', comment('a2'));
    expect(ids(result[0].replies ?? [])).toEqual(['a2', 'a1']);
  });

  it('gives a first reply to a comment without replies', () => {
    const result = insertReply([comment('a')], 'a', comment('a1'));
    expect(ids(result[0].replies ?? [])).toEqual(['a1']);
  });

  it('inserts a reply four levels deep', () => {
    const result = insertReply(deepTree(), 'd', comment('new'));
    const path = findPath(result, 'new');
    expect(ids(path ?? [])).toEqual(['a', 'b', 'c', 'd', 'new']);
  });

  it('returns the same roots when the parent is not found', () => {
    const roots = deepTree();
    expect(insertReply(roots, 'missing', comment('new'))).toBe(roots);
  });

  it('leaves the original tree unchanged', () => {
    const roots = deepTree();
    const snapshot = JSON.parse(JSON.stringify(roots));
    const result = insertReply(roots, 'd', comment('new'));
    expect(roots).toEqual(snapshot);
    expect(result).not.toBe(roots);
  });

  it('keeps the nodes off the path shared with the original tree', () => {
    const roots = deepTree();
    const result = insertReply(roots, 'd', comment('new'));
    expect(result[1]).toBe(roots[1]);
  });
});

describe('replaceComment', () => {
  it('replaces a deep comment and keeps its cached replies', () => {
    const roots = deepTree();
    const updated = comment('c', undefined, { message: 'edited', vote_score: 5 });
    const result = replaceComment(roots, updated);
    const replaced = findPath(result, 'c')?.[2];
    expect(replaced?.message).toBe('edited');
    expect(replaced?.vote_score).toBe(5);
    expect(ids(replaced?.replies ?? [])).toEqual(['d']);
  });

  it('keeps the cached replies even when the update carries other ones', () => {
    const result = replaceComment(deepTree(), comment('a', [comment('z')]));
    expect(ids(result[0].replies ?? [])).toEqual(['b']);
  });

  it('returns the same roots when no comment has that id', () => {
    const roots = deepTree();
    expect(replaceComment(roots, comment('missing'))).toBe(roots);
  });

  it('leaves the original tree unchanged', () => {
    const roots = deepTree();
    const snapshot = JSON.parse(JSON.stringify(roots));
    replaceComment(roots, comment('d', undefined, { message: 'edited' }));
    expect(roots).toEqual(snapshot);
  });
});
