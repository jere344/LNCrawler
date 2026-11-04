import { describe, expect, it } from 'vitest';
import type { Comment } from '@models/comments_types';
import { threadAfterReply } from './threadDepth';

const comment = (id: string): Comment => ({
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
});

// A chain of comments from a root down: depth 0 is `a`
const chain = (...ids: string[]): Comment[] => ids.map(comment);

describe('threadAfterReply', () => {
  it('keeps a shallow reply in the list view', () => {
    // Parent `b` sits at depth 1, under the maximum of 3
    expect(threadAfterReply(chain('a', 'b'), null, 3)).toBeNull();
  });

  it('opens the parent when a reply in the list view would sit past the maximum', () => {
    // Parent `d` sits at depth 3, so its reply would be at depth 4
    expect(threadAfterReply(chain('a', 'b', 'c', 'd'), null, 3)).toBe('d');
  });

  it('keeps a reply at exactly the maximum when the parent is above it', () => {
    // Parent `c` sits at depth 2, its reply at depth 3 is shown
    expect(threadAfterReply(chain('a', 'b', 'c'), null, 3)).toBeNull();
  });

  it('measures the depth from the thread view root', () => {
    // View root `b` is at index 1: the parent `d` is at relative depth 2, under a maximum of 3
    expect(threadAfterReply(chain('a', 'b', 'c', 'd'), 'b', 3)).toBeNull();
    // With a maximum of 2 the same reply is past it
    expect(threadAfterReply(chain('a', 'b', 'c', 'd'), 'b', 2)).toBe('d');
  });

  it('returns null when the parent is not in the path', () => {
    expect(threadAfterReply([], null, 3)).toBeNull();
    expect(threadAfterReply([], 'b', 3)).toBeNull();
  });

  it('returns null when the thread view root is not in the path', () => {
    expect(threadAfterReply(chain('a', 'b', 'c', 'd'), 'z', 2)).toBeNull();
  });
});
