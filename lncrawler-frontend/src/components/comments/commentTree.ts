import type { Comment } from '@models/comments_types';

// The chain of comments from a root down to the comment with `id`; null when it is not in the tree
export function findPath(roots: Comment[], id: string): Comment[] | null {
  for (const root of roots) {
    if (root.id === id) return [root];
    const inner = root.replies ? findPath(root.replies, id) : null;
    if (inner) return [root, ...inner];
  }
  return null;
}

// Every reply under a comment, at any depth
export function countDescendants(comment: Comment): number {
  return (comment.replies ?? []).reduce((total, reply) => total + 1 + countDescendants(reply), 0);
}

// Adds `reply` at the start of the parent's replies, the server's order (newest first); only the nodes on the path are copied
export function insertReply(roots: Comment[], parentId: string, reply: Comment): Comment[] {
  return insertInto(roots, parentId, reply) ?? roots;
}

// Swaps in the comment with the same id; the replies already shown are kept, whatever the update carries
export function replaceComment(roots: Comment[], updated: Comment): Comment[] {
  return replaceIn(roots, updated) ?? roots;
}

// The list with the reply added, or null when the parent is not in this list
function insertInto(list: Comment[], parentId: string, reply: Comment): Comment[] | null {
  for (let index = 0; index < list.length; index++) {
    const node = list[index];
    let next: Comment | null = null;
    if (node.id === parentId) {
      next = { ...node, replies: [reply, ...(node.replies ?? [])] };
    } else if (node.replies) {
      const replies = insertInto(node.replies, parentId, reply);
      if (replies) next = { ...node, replies };
    }
    if (next) {
      const replacement = next;
      return list.map((item, i) => (i === index ? replacement : item));
    }
  }
  return null;
}

// The list with the node replaced, or null when no node has that id
function replaceIn(list: Comment[], updated: Comment): Comment[] | null {
  for (let index = 0; index < list.length; index++) {
    const node = list[index];
    let next: Comment | null = null;
    if (node.id === updated.id) {
      next = { ...updated, replies: node.replies };
    } else if (node.replies) {
      const replies = replaceIn(node.replies, updated);
      if (replies) next = { ...node, replies };
    }
    if (next) {
      const replacement = next;
      return list.map((item, i) => (i === index ? replacement : item));
    }
  }
  return null;
}
