import { describe, expect, it } from 'vitest';
import type { Comment } from '@models/comments_types';
import type { User } from '@models/user_types';
import { commentAuthorName, isOwnComment, resolveAuthorName } from './commentAuthor';

const account = { id: '1', username: 'alice', profile_pic: '' } as User;
const otherAccount = { id: '2', username: 'bob', profile_pic: '' } as User;

const commentBy = (user: User | null, authorName = 'guest-name') =>
  ({ id: 'c1', author_name: authorName, user }) as Comment;

describe('commentAuthorName', () => {
  it('uses the username of the account', () => {
    expect(commentAuthorName(commentBy(account, 'alice-typed'))).toBe('alice');
  });

  it('uses the name written by a guest', () => {
    expect(commentAuthorName(commentBy(null, 'Guest'))).toBe('Guest');
  });

  it('falls back to the name written when the account has no username', () => {
    expect(commentAuthorName(commentBy({ ...account, username: '' }, 'Fallback'))).toBe('Fallback');
  });
});

describe('isOwnComment', () => {
  it('is true for a comment written by the signed-in account', () => {
    expect(isOwnComment(commentBy(account), account)).toBe(true);
  });

  it('is false for a comment written by another account', () => {
    expect(isOwnComment(commentBy(otherAccount), account)).toBe(false);
  });

  it('is false for a guest comment', () => {
    expect(isOwnComment(commentBy(null), account)).toBe(false);
  });

  it('is false when nobody is signed in', () => {
    expect(isOwnComment(commentBy(account), null)).toBe(false);
  });
});

describe('resolveAuthorName', () => {
  it('uses the username when signed in', () => {
    expect(resolveAuthorName(true, account, 'typed')).toBe('alice');
  });

  it('uses the typed name when not signed in', () => {
    expect(resolveAuthorName(false, null, 'typed')).toBe('typed');
  });

  it('uses the typed name when flagged as signed in but no user is loaded', () => {
    expect(resolveAuthorName(true, null, 'typed')).toBe('typed');
  });
});
