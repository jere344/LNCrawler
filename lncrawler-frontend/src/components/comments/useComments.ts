import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import type { Comment, CommentFormData } from '@models/comments_types';
import { commentService } from '@services/comment.service';
import { commentsCache } from './comments';
import type { CommentTarget, CommentsState } from './commentsCache';

// The target the hook shows; `id` tells one from another
interface Shown {
  id: string;
  target: CommentTarget;
}

export interface CommentsView {
  roots: Comment[];
  loading: boolean;
  // The load's error: the list is not shown, and only while nothing is loaded for the target
  error: unknown;
  // Sends the comments again after a failure
  retry: () => void;
  post: (data: CommentFormData) => Promise<Comment>;
  update: (comment: Comment) => void;
}

const NO_ROOTS: Comment[] = [];

// The id of a target: the sources of a chapter have their own, as they are asked for separately
const shownId = (target: CommentTarget): string =>
  JSON.stringify(
    target.kind === 'chapter'
      ? [target.novelSlug, target.sourceSlug, target.chapterNumber]
      : [target.novelSlug],
  );

// Comments of a chapter or a novel. The state comes from the shared cache, so a target already loaded shows at once.
export function useComments(target: CommentTarget | null): CommentsView {
  const id = target ? shownId(target) : null;
  const shown = useMemo<Shown | null>(
    () => (target && id ? { id, target } : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the id stands for the target
    [id],
  );

  // Bumped after a change in the cache, so the state is read again
  const [, refresh] = useReducer((version: number) => version + 1, 0);
  // The id of the target shown: a response for an older target is dropped
  const activeId = useRef<string | null>(null);
  // The target whose load failed
  const [failed, setFailed] = useState<{ id: string; error: unknown } | null>(null);

  useEffect(() => {
    activeId.current = shown?.id ?? null;
  }, [shown]);

  // Requests the comments of a target; a response for a target no longer shown is dropped
  const loadComments = useCallback((next: Shown) => {
    const { id: nextId, target: nextTarget } = next;
    commentsCache.load(nextTarget).then(
      () => {
        if (activeId.current === nextId) refresh();
      },
      (error: unknown) => {
        if (activeId.current === nextId) setFailed({ id: nextId, error });
      },
    );
  }, []);

  useEffect(() => {
    if (shown) loadComments(shown);
  }, [shown, loadComments]);

  // A new attempt starts without the failure of the last one
  const retry = useCallback(() => {
    if (!shown) return;
    setFailed(null);
    loadComments(shown);
  }, [shown, loadComments]);

  // Read on every render: the cache holds the state of the target shown, whatever was shown before
  const state: CommentsState | null = shown ? commentsCache.peek(shown.target) ?? null : null;
  // A failure only blocks the list while nothing is loaded for the target: a state that exists is shown
  const error = state === null && shown && failed?.id === shown.id ? failed.error : null;

  // Posts a root comment or a reply to the target; the cache takes the created comment without a reload
  const post = useCallback(async (data: CommentFormData): Promise<Comment> => {
    if (!shown) throw new Error('No comments target to post to');
    const { id: postedId, target: postedTarget } = shown;
    const comment = postedTarget.kind === 'chapter'
      ? await commentService.addChapterComment(postedTarget.novelSlug, postedTarget.sourceSlug, postedTarget.chapterNumber, data)
      : await commentService.addNovelComment(postedTarget.novelSlug, data);
    if (data.parent_id) commentsCache.addReply(postedTarget, data.parent_id, comment);
    else commentsCache.addRoot(postedTarget, comment);
    if (activeId.current === postedId) refresh();
    return comment;
  }, [shown]);

  // Puts an updated comment (vote, edit) in place, keeping the replies shown
  const update = useCallback((comment: Comment) => {
    if (!shown) return;
    commentsCache.replace(shown.target, comment);
    refresh();
  }, [shown]);

  return {
    roots: state?.roots ?? NO_ROOTS,
    loading: shown !== null && state === null && error === null,
    error,
    retry,
    post,
    update,
  };
}
