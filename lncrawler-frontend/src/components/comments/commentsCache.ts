import type { Comment, CommentOrdering } from '@models/comments_types';
import { insertReply, replaceComment } from './commentTree';
import { createSharedRequests, type SharedRequests } from '@utils/sharedRequest';

// Every ordering a target's comments are cached in: a change is applied to each one that is loaded
const ORDERINGS: CommentOrdering[] = ['top', 'new'];

// Where comments are posted: a chapter (every source with this chapter number shares them) or a novel
export type CommentTarget =
  | { kind: 'chapter'; novelSlug: string; sourceSlug: string; chapterNumber: number }
  | { kind: 'novel'; novelSlug: string };

// What is known about one target and ordering: every root comment, with its replies
export interface CommentsState {
  roots: Comment[];
}

// The root comments of a target, with their replies, in the ordering asked for
type CommentsFetcher = (target: CommentTarget, ordering: CommentOrdering) => Promise<Comment[]>;

export interface CommentsCache {
  // The stored state for a target and ordering, if it is loaded already; never sends a request
  peek: (target: CommentTarget, ordering: CommentOrdering) => CommentsState | undefined;
  // The comments once; concurrent callers share the request
  load: (target: CommentTarget, ordering: CommentOrdering) => Promise<CommentsState>;
  // A new root comment, shown first in every loaded ordering
  addRoot: (target: CommentTarget, comment: Comment) => void;
  // A new reply under `parentId` in every loaded ordering
  addReply: (target: CommentTarget, parentId: string, reply: Comment) => void;
  // An updated comment in every loaded ordering
  replace: (target: CommentTarget, comment: Comment) => void;
}

// Entries are kept per target and ordering: the source of a chapter is not part of the key
const entryKey = (target: CommentTarget, ordering: CommentOrdering) =>
  JSON.stringify(
    target.kind === 'chapter'
      ? [target.novelSlug, 'chapter', target.chapterNumber, ordering]
      : [target.novelSlug, 'novel', ordering],
  );

// Creates a cache around `fetchComments`. Only successful responses are kept: a failed request is simply sent again.
export function createCommentsCache(fetchComments: CommentsFetcher): CommentsCache {
  const entries = new Map<string, CommentsState>();
  // The requests on their way, shared by every caller that asks for the same entry
  const inflight: SharedRequests<CommentsState> = createSharedRequests();

  // Applies a change to every loaded ordering of the target; a state the change leaves as it was is kept
  const update = (target: CommentTarget, change: (state: CommentsState) => CommentsState) => {
    for (const ordering of ORDERINGS) {
      const id = entryKey(target, ordering);
      const state = entries.get(id);
      if (state) entries.set(id, change(state));
    }
  };

  // The state with new roots, or the same state when the change did not alter them
  const withRoots = (state: CommentsState, roots: Comment[]): CommentsState =>
    roots === state.roots ? state : { ...state, roots };

  return {
    peek: (target, ordering) => entries.get(entryKey(target, ordering)),

    load: (target, ordering) => {
      const id = entryKey(target, ordering);
      const existing = entries.get(id);
      if (existing) return Promise.resolve(existing);
      return inflight.run(
        id,
        () => fetchComments(target, ordering),
        (roots) => {
          const state: CommentsState = { roots };
          entries.set(id, state);
          return state;
        },
      );
    },

    addRoot: (target, comment) =>
      update(target, (state) =>
        state.roots.some((root) => root.id === comment.id)
          ? state
          : { ...state, roots: [comment, ...state.roots] },
      ),

    addReply: (target, parentId, reply) =>
      update(target, (state) => withRoots(state, insertReply(state.roots, parentId, reply))),

    replace: (target, comment) =>
      update(target, (state) => withRoots(state, replaceComment(state.roots, comment))),
  };
}
