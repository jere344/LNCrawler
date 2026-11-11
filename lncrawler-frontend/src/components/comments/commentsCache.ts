import type { Comment } from '@models/comments_types';
import { insertReply, replaceComment } from './commentTree';
import { createSharedRequests, type SharedRequests } from '@utils/sharedRequest';

// Where comments are posted: a chapter (every source with this chapter number shares them) or a novel
export type CommentTarget =
  | { kind: 'chapter'; novelSlug: string; sourceSlug: string; chapterNumber: number }
  | { kind: 'novel'; novelSlug: string };

// What is known about one target: every root comment, with its replies
export interface CommentsState {
  roots: Comment[];
}

// The root comments of a target, with their replies
type CommentsFetcher = (target: CommentTarget) => Promise<Comment[]>;

export interface CommentsCache {
  // The stored state for a target, if it is loaded already; never sends a request
  peek: (target: CommentTarget) => CommentsState | undefined;
  // The comments once; concurrent callers share the request
  load: (target: CommentTarget) => Promise<CommentsState>;
  // A new root comment, shown first
  addRoot: (target: CommentTarget, comment: Comment) => void;
  // A new reply under `parentId`
  addReply: (target: CommentTarget, parentId: string, reply: Comment) => void;
  // An updated comment
  replace: (target: CommentTarget, comment: Comment) => void;
}

// Entries are kept per target: the source of a chapter is not part of the key
const entryKey = (target: CommentTarget) =>
  JSON.stringify(
    target.kind === 'chapter'
      ? [target.novelSlug, 'chapter', target.chapterNumber]
      : [target.novelSlug, 'novel'],
  );

// Creates a cache around `fetchComments`. Only successful responses are kept: a failed request is simply sent again.
export function createCommentsCache(fetchComments: CommentsFetcher): CommentsCache {
  const entries = new Map<string, CommentsState>();
  // The requests on their way, shared by every caller that asks for the same entry
  const inflight: SharedRequests<CommentsState> = createSharedRequests();

  // Applies a change to the loaded state of the target; a state the change leaves as it was is kept
  const update = (target: CommentTarget, change: (state: CommentsState) => CommentsState) => {
    const id = entryKey(target);
    const state = entries.get(id);
    if (state) entries.set(id, change(state));
  };

  // The state with new roots, or the same state when the change did not alter them
  const withRoots = (state: CommentsState, roots: Comment[]): CommentsState =>
    roots === state.roots ? state : { ...state, roots };

  return {
    peek: (target) => entries.get(entryKey(target)),

    load: (target) => {
      const id = entryKey(target);
      const existing = entries.get(id);
      if (existing) return Promise.resolve(existing);
      return inflight.run(
        id,
        () => fetchComments(target),
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
