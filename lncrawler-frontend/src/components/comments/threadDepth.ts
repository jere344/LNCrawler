import type { Comment } from '@models/comments_types';

// The parent id to open as a thread once a reply is posted under it, or null when the reply shows in place.
// `path` runs from a root down to the parent; the depth is counted from the thread view's root (the list's roots at null).
export function threadAfterReply(path: Comment[], viewRootId: string | null, maxDepth: number): string | null {
  if (path.length === 0) return null;
  // The view root is the top of the thread view: a parent above it, or outside the path, has no place to show
  const viewRoot = viewRootId === null ? 0 : path.findIndex((comment) => comment.id === viewRootId);
  if (viewRoot < 0) return null;
  const parent = path[path.length - 1];
  const depth = path.length - 1 - viewRoot;
  return depth >= maxDepth ? parent.id : null;
}
