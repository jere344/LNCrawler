import { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Divider, Typography, useMediaQuery, useTheme } from '@mui/material';
import type { Comment, CommentFormData } from '@models/comments_types';
import CommentThreads, { type CommentThreadsHandle } from './CommentThreads';
import CommentComposer from './CommentComposer';
import { useComments } from './useComments';
import { useReplyTarget } from './useReplyTarget';
import type { CommentTarget } from './commentsCache';

interface CommentSectionProps {
  novelSlug: string;
  title: string;
}

// The comments of a novel, under its page: the page scrolls, and a thread opens in place
const CommentSection = ({ novelSlug, title }: CommentSectionProps) => {
  const theme = useTheme();
  // Replies nest deeper on wider screens before a thread opens of its own
  const wide = useMediaQuery(theme.breakpoints.up('sm'), { noSsr: true });
  const target = useMemo<CommentTarget>(() => ({ kind: 'novel', novelSlug }), [novelSlug]);
  const comments = useComments(target);
  // The thread levels open, the last one on screen: kept here, as the page has no history of them
  const [threads, setThreads] = useState<string[]>([]);
  const [composing, setComposing] = useState(false);
  const { replyTo, setReplyTo } = useReplyTarget(composing);
  const threadsRef = useRef<CommentThreadsHandle>(null);

  // Another novel starts with nothing open
  useEffect(() => {
    setThreads([]);
    setComposing(false);
  }, [novelSlug]);

  // Reply opens the composer, with the comment named above the field
  const handleReply = (comment: Comment) => {
    setReplyTo(comment);
    setComposing(true);
  };

  // Posts the comment. A reply the thread view would not show opens its parent as a thread of its own.
  const handleSubmit = async (data: CommentFormData) => {
    const created = await comments.post(data);
    const thenThread = threadsRef.current?.reveal(created, data.parent_id ?? null) ?? null;
    setComposing(false);
    if (thenThread) setThreads((previous) => [...previous, thenThread]);
  };

  const pushThread = (id: string) => setThreads((previous) => [...previous, id]);
  const popThread = () => setThreads((previous) => previous.slice(0, -1));

  return (
    <Box sx={{ mt: 4, mb: 6 }}>
      <Typography variant="h5" gutterBottom>
        {title}
      </Typography>

      <Divider sx={{ mb: 3 }} />

      <Box sx={{ mb: 2 }}>
        <CommentComposer
          target={target}
          open={composing}
          replyTo={replyTo}
          onOpen={() => setComposing(true)}
          onCancelReply={() => setReplyTo(null)}
          onClose={() => setComposing(false)}
          onSubmit={handleSubmit}
        />
      </Box>

      <CommentThreads
        ref={threadsRef}
        target={target}
        comments={comments}
        threads={threads}
        onPushThread={pushThread}
        onPopThread={popThread}
        maxDepth={wide ? 5 : 3}
        showChapterLabel
        onReply={handleReply}
      />
    </Box>
  );
};

export default CommentSection;
