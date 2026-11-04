import { commentService } from '@services/comment.service';
import { createCommentsCache, type CommentTarget } from './commentsCache';

// Shared by every visit: comments reopened in the same session make no request
export const commentsCache = createCommentsCache((target, ordering) =>
  target.kind === 'chapter'
    ? commentService.getChapterComments(target.novelSlug, target.sourceSlug, target.chapterNumber, { ordering })
    : commentService.getNovelComments(target.novelSlug, { ordering }),
);

// Unsent comment text per target and parent, kept while the reader moves between chapters
const drafts = new Map<string, string>();

// The slot of a target's drafts: every source of a chapter shares them, as it shares its comments
export const targetSlot = (target: CommentTarget): string =>
  JSON.stringify(target.kind === 'chapter' ? [target.novelSlug, target.chapterNumber] : [target.novelSlug, 'novel']);

// The key of a draft: a new comment and each reply to a comment have their own
export const draftKey = (target: CommentTarget, parentId: string | undefined): string =>
  JSON.stringify([targetSlot(target), parentId ?? 'root']);

// The unsent text for a target and parent comment (none for a new comment), or '' when there is none
export function getDraft(target: CommentTarget, parentId?: string): string {
  return drafts.get(draftKey(target, parentId)) ?? '';
}

// Keeps the text for a target and parent; empty or blank text clears the draft
export function setDraft(target: CommentTarget, parentId: string | undefined, text: string): void {
  if (text.trim() === '') drafts.delete(draftKey(target, parentId));
  else drafts.set(draftKey(target, parentId), text);
}
