import type { Comment } from '@models/comments_types';
import type { User } from '@models/user_types';

// The name shown for a comment: the account's username, or the name a guest wrote
export const commentAuthorName = (comment: Pick<Comment, 'user' | 'author_name'>): string =>
  comment.user?.username || comment.author_name;

// True when the comment was written by this account
export const isOwnComment = (comment: Pick<Comment, 'user'>, user: User | null): boolean =>
  !!user && !!comment.user && user.username === comment.user.username;

// The author name sent with a new comment: the account's username when signed in, else the name typed
export const resolveAuthorName = (isAuthenticated: boolean, user: User | null, guestName: string): string =>
  isAuthenticated && user ? user.username : guestName;
