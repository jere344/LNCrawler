import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Box, IconButton } from '@mui/material';
import { useTranslation } from 'react-i18next';
import CloseIcon from '@mui/icons-material/Close';
import type { Comment, CommentFormData, CommentOrdering } from '@models/comments_types';
import CommentThreads, { type CommentThreadsHandle } from '@components/comments/CommentThreads';
import CommentComposer from '@components/comments/CommentComposer';
import { useComments } from '@components/comments/useComments';
import { useReplyTarget } from '@components/comments/useReplyTarget';
import type { CommentTarget } from '@components/comments/commentsCache';
import type { ReaderLayoutMode } from '../hooks/useReaderLayout';
import ReaderPanelFrame from '../panels/ReaderPanelFrame';
import ReaderPanelHeader from '../panels/ReaderPanelHeader';
import ReaderBottomSheet from '../panels/ReaderBottomSheet';
import { commentsWidth } from '../panels/panelLayout';

// The sort chosen in this session, kept when the panel closes and opens again
let sessionOrdering: CommentOrdering = 'top';

export interface CommentsPanelProps {
  mode: ReaderLayoutMode;
  novelSlug: string;
  sourceSlug: string;
  chapterNumber: number;
  // The chapter's title, shown in the caption
  chapterLabel: string;
  totalCount: number;
  // Comment ids opened as thread views, the last one on screen
  threads: string[];
  // The composer is open
  composing: boolean;
  // Space kept under the phone sheet, for the TTS bar
  bottomOffset?: number;
  onClose: () => void;
  // Up one level, as Back
  onBack: () => void;
  onPushThread: (id: string) => void;
  onStartComposing: () => void;
  onStopComposing: (options?: { thenThread?: string }) => void;
  // A comment was posted to this chapter
  onPosted: (chapterNumber: number) => void;
}

// The comments of a chapter in a reader panel: a phone shows them as a bottom sheet, wider layouts as a side panel.
// The thread levels are the reader's history, so Back goes up one level.
const CommentsPanel = ({
  mode,
  novelSlug,
  sourceSlug,
  chapterNumber,
  chapterLabel,
  totalCount,
  threads,
  composing,
  bottomOffset,
  onClose,
  onBack,
  onPushThread,
  onStartComposing,
  onStopComposing,
  onPosted,
}: CommentsPanelProps) => {
  const { t } = useTranslation();
  const [ordering, setOrdering] = useState<CommentOrdering>(sessionOrdering);
  const target: CommentTarget = { kind: 'chapter', novelSlug, sourceSlug, chapterNumber };
  const comments = useComments(target, ordering);
  // Deeper replies are shown on wide layouts before they open as a thread of their own
  const maxDepth = mode === 'phone' ? 3 : 5;
  const { replyTo, setReplyTo } = useReplyTarget(composing);
  // Phone only: the sheet is at full height
  const [full, setFull] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const threadsRef = useRef<CommentThreadsHandle>(null);
  // Mount state and the composer's state as of now, read after an await in handleSubmit
  const mounted = useRef(false);
  const composingRef = useRef(composing);
  useLayoutEffect(() => {
    composingRef.current = composing;
  });
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // The sort is kept for the session
  const changeOrdering = (value: CommentOrdering) => {
    sessionOrdering = value;
    setOrdering(value);
  };

  // Reply opens the composer, with the comment named above the field
  const handleReply = (comment: Comment) => {
    setReplyTo(comment);
    if (!composing) onStartComposing();
  };

  // Posts the comment. A reply the thread view would not show opens its parent as a thread of its own.
  const handleSubmit = async (data: CommentFormData) => {
    const created = await comments.post(data);
    // Counted for the chapter it was posted to, whatever is on screen by now
    onPosted(chapterNumber);
    // The panel is gone or the composer closed meanwhile: the comment is kept, and nothing else moves
    if (!mounted.current || !composingRef.current) return;
    const thenThread = threadsRef.current?.reveal(created, data.parent_id ?? null) ?? null;
    onStopComposing({ thenThread: thenThread ?? undefined });
  };

  const title = t('readerComments.title');

  // On phones the header is inside the sheet, below its drag handle
  const phoneHeader = (
    <ReaderPanelHeader
      title={title}
      close={{ label: t('readerComments.close'), onClick: onClose, ref: closeRef }}
      sx={{ flex: 'none', px: 2, pt: 0.5, pb: 1 }}
    />
  );

  const body = (
    <>
      {mode === 'phone' && phoneHeader}

      <CommentThreads
        ref={threadsRef}
        target={target}
        comments={comments}
        ordering={ordering}
        onOrderingChange={changeOrdering}
        threads={threads}
        onPushThread={onPushThread}
        onPopThread={onBack}
        maxDepth={maxDepth}
        currentSource={sourceSlug}
        onReply={handleReply}
        caption={`${chapterLabel} · ${t('readerComments.count', { count: totalCount })}`}
        scrollRef={listRef}
      />

      <Box
        sx={{
          flex: 'none',
          borderTop: 1,
          borderColor: 'divider',
          bgcolor: 'background.paper',
          px: 2,
          pt: 1.5,
          pb: 'calc(12px + env(safe-area-inset-bottom))',
        }}
      >
        <CommentComposer
          target={target}
          open={composing}
          replyTo={replyTo}
          onOpen={onStartComposing}
          onCancelReply={() => setReplyTo(null)}
          onClose={() => onStopComposing()}
          onSubmit={handleSubmit}
        />
      </Box>
    </>
  );

  if (mode === 'phone') {
    return (
      <ReaderBottomSheet
        title={title}
        full={full}
        onFullChange={setFull}
        onClose={onClose}
        composing={composing}
        onStopComposing={() => onStopComposing()}
        focusRef={closeRef}
        bottomOffset={bottomOffset}
      >
        {body}
      </ReaderBottomSheet>
    );
  }

  return (
    <ReaderPanelFrame
      title={title}
      mode={mode}
      side="end"
      width={commentsWidth(mode) ?? undefined}
      showBack={false}
      flush
      headerExtra={
        <IconButton onClick={onClose} aria-label={t('readerComments.close')}>
          <CloseIcon />
        </IconButton>
      }
    >
      {body}
    </ReaderPanelFrame>
  );
};

export default CommentsPanel;
