import { useImperativeHandle, useRef, useState, type ReactNode, type Ref, type RefObject } from 'react';
import { Box, Button, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import type { Comment } from '@models/comments_types';
import { TOUCH_MIN_HEIGHT } from '@components/reader/touchTarget';
import DirectionalIcon from '@components/reader/DirectionalIcon';
import { commentAuthorName } from './commentAuthor';
import { findPath } from './commentTree';
import type { CommentTarget } from './commentsCache';
import type { CommentsView } from './useComments';
import ThreadComment from './ThreadComment';
import CenteredNote from './CenteredNote';
import CommentRowSkeleton from './CommentRowSkeleton';
import { useThreadNavigation } from './useThreadNavigation';
import { useCommentListScroll } from './useCommentListScroll';
import { threadAfterReply } from './threadDepth';

const SKELETON_ROWS = 4;

// What a parent calls after posting a comment
export interface CommentThreadsHandle {
  // Shows a comment just posted under `parentId` (null for a root): its parent and the comments above it are opened, and it is highlighted.
  // Returns the parent to open as a thread of its own, when the reply would not show in place.
  reveal: (created: Comment, parentId: string | null) => string | null;
}

interface CommentThreadsProps {
  target: CommentTarget;
  comments: CommentsView;
  // Comment ids opened as thread views, the last one on screen
  threads: string[];
  onPushThread: (id: string) => void;
  // Up one thread level, as the thread bar's Back button
  onPopThread: () => void;
  // Levels of replies shown under a comment before its replies open as a thread of their own
  maxDepth: number;
  // The source of the chapter read: comments from other sources are marked
  currentSource?: string;
  // Names the chapter and source of a chapter comment (novel page)
  showChapterLabel?: boolean;
  onReply: (comment: Comment) => void;
  // Shown at the start of the toolbar
  caption?: string;
  // The element the comments scroll in; the page scrolls when there is none
  scrollRef?: RefObject<HTMLDivElement | null>;
  ref?: Ref<CommentThreadsHandle>;
}

// The set with the id in it; the same set when it is there already
const withId = (set: Set<string>, id: string) => (set.has(id) ? set : new Set(set).add(id));

// The set without the id; the same set when it is not there
const withoutId = (set: Set<string>, id: string) => {
  if (!set.has(id)) return set;
  const next = new Set(set);
  next.delete(id);
  return next;
};

// The sorted comments of a chapter or a novel, opened thread by thread. The list is laid out by the parent: in a scroll container, or on the page.
const CommentThreads = ({
  target,
  comments,
  threads,
  onPushThread,
  onPopThread,
  maxDepth,
  currentSource,
  showChapterLabel = false,
  onReply,
  caption,
  scrollRef,
  ref,
}: CommentThreadsProps) => {
  const { t } = useTranslation();
  const { roots, loading, error, retry, update } = comments;
  // Comments collapsed to a row, and comments with all their replies shown
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const rootRef = useRef<HTMLDivElement>(null);
  const threadBackRef = useRef<HTMLButtonElement>(null);
  // The room kept at the sides: in a scroll container only
  const inset = scrollRef ? 2 : 0;
  const inThread = threads.length > 0;
  const currentThread = threads[threads.length - 1] as string | undefined;
  // The comment the thread view opens on, when it is among the comments loaded
  const threadRoot = currentThread === undefined ? null : (findPath(roots, currentThread)?.slice(-1)[0] ?? null);

  const { trackScroll } = useThreadNavigation(threads, { scrollRef, rootRef, threadBackRef });
  const { highlightId, highlight } = useCommentListScroll(scrollRef, roots, threads);

  // The parent calls this once a comment is posted: the reply shows in place, or its parent opens as a thread
  const reveal = (created: Comment, parentId: string | null): string | null => {
    const path = parentId ? (findPath(roots, parentId) ?? []) : [];
    const thenThread = parentId ? threadAfterReply(path, currentThread ?? null, maxDepth) : null;
    if (parentId) {
      // The parent and the comments above it are opened, so the reply shows under them
      setHidden((prev) => path.reduce((set, comment) => withoutId(set, comment.id), prev));
      setExpanded((prev) => withId(prev, parentId));
    }
    highlight(created.id);
    return thenThread;
  };
  useImperativeHandle(ref, () => ({ reveal }));

  const toggleHidden = (id: string) => {
    setHidden((prev) => (prev.has(id) ? withoutId(prev, id) : withId(prev, id)));
  };

  const showAll = (id: string) => {
    setExpanded((prev) => withId(prev, id));
  };

  const sharedThreadProps = {
    maxDepth,
    currentSource,
    showChapterLabel,
    hidden,
    expanded,
    highlightId,
    onToggleHidden: toggleHidden,
    onShowAll: showAll,
    onContinue: onPushThread,
    onReply,
    onUpdate: update,
  };

  const skeletons = Array.from({ length: SKELETON_ROWS }, (_, index) => <CommentRowSkeleton key={index} />);
  // The load failed: the comments are not shown, and the retry is offered
  const loadFailed = (
    <CenteredNote
      error
      action={
        <Button size="small" onClick={() => { void retry(); }} sx={{ mt: 1, minHeight: TOUCH_MIN_HEIGHT }}>
          {t('readerChapters.retry')}
        </Button>
      }
    >
      {t('comments.loadFailed')}
    </CenteredNote>
  );

  let listContent: ReactNode;
  if (inThread) {
    if (loading) listContent = skeletons;
    else if (error) listContent = loadFailed;
    else if (threadRoot) listContent = <ThreadComment comment={threadRoot} depth={0} {...sharedThreadProps} />;
    else listContent = <CenteredNote>{t('readerComments.notLoaded')}</CenteredNote>;
  } else if (loading) {
    listContent = skeletons;
  } else if (error) {
    listContent = loadFailed;
  } else if (roots.length === 0) {
    listContent = (
      <CenteredNote>
        {target.kind === 'chapter'
          ? t('readerComments.empty', { chapter: target.chapterNumber })
          : t('comments.noComments')}
      </CenteredNote>
    );
  } else {
    listContent = (
      <>
        {roots.map((root) => (
          <ThreadComment key={root.id} comment={root} depth={0} {...sharedThreadProps} />
        ))}
        <CenteredNote>
          {target.kind === 'chapter' ? t('readerComments.end') : t('comments.end')}
        </CenteredNote>
      </>
    );
  }

  return (
    <Box ref={rootRef} sx={scrollRef ? { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' } : undefined}>
      {caption && (
        <Box sx={{ flex: 'none', display: 'flex', alignItems: 'center', gap: 1, minWidth: 0, px: inset, pb: 1 }}>
          <Typography variant="caption" noWrap sx={{ flex: 1, minWidth: 0, color: 'text.secondary' }}>
            {caption}
          </Typography>
        </Box>
      )}

      <Box
        ref={scrollRef}
        // Focused when a thread closes and nothing in the list can take its place
        tabIndex={scrollRef ? -1 : undefined}
        onScroll={trackScroll}
        sx={scrollRef
          ? {
            flex: 1,
            minHeight: 0,
            overflowY: 'auto',
            overscrollBehavior: 'contain',
            px: 2,
            scrollbarWidth: 'thin',
          }
          : undefined}
      >
        {inThread && (
          <Box
            sx={{
              position: scrollRef ? 'sticky' : 'static',
              top: 0,
              zIndex: 1,
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              minWidth: 0,
              marginInline: -inset,
              paddingInline: inset,
              py: 1,
              bgcolor: scrollRef ? 'background.paper' : undefined,
              borderBottom: 1,
              borderColor: 'divider',
            }}
          >
            <Button
              ref={threadBackRef}
              size="small"
              onClick={onPopThread}
              startIcon={<DirectionalIcon><ArrowBackIcon /></DirectionalIcon>}
              sx={{ flex: 'none', minHeight: TOUCH_MIN_HEIGHT }}
            >
              {threads.length > 1 ? t('readerComments.back') : t('readerComments.allComments')}
            </Button>
            {threadRoot && (
              <Typography variant="body2" noWrap sx={{ minWidth: 0, color: 'text.secondary' }}>
                {t('readerComments.threadFrom', { name: commentAuthorName(threadRoot) })}
              </Typography>
            )}
          </Box>
        )}

        {listContent}
      </Box>
    </Box>
  );
};

export default CommentThreads;
