import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Alert, Box, Button, ButtonBase, CircularProgress, IconButton, TextField, ToggleButton, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import ReplyIcon from '@mui/icons-material/Reply';
import CloseIcon from '@mui/icons-material/Close';
import type { Comment, CommentFormData } from '@models/comments_types';
import { useAuth } from '@context/AuthContext';
import { getApiErrorMessage } from '@utils/apiError';
import { TOUCH_MIN_HEIGHT, TOUCH_TARGET } from '@components/reader/touchTarget';
import { commentAuthorName, resolveAuthorName } from './commentAuthor';
import { draftKey, getDraft, setDraft } from './comments';
import type { CommentTarget } from './commentsCache';

interface CommentComposerProps {
  // Where the comment goes: its drafts are kept per target
  target: CommentTarget;
  open: boolean;
  // The comment being replied to, named above the field
  replyTo: Comment | null;
  onOpen: () => void;
  onCancelReply: () => void;
  onClose: () => void;
  onSubmit: (data: CommentFormData) => Promise<void>;
}

type ComposerFormProps = Omit<CommentComposerProps, 'open' | 'onOpen'>;

// The open composer: the text field, a name for guests, the spoiler flag and Post. The text is kept as a draft as it is typed.
const ComposerForm = ({ target, replyTo, onCancelReply, onClose, onSubmit }: ComposerFormProps) => {
  const { t } = useTranslation();
  const { isAuthenticated, user } = useAuth();
  // Seeded from the draft of this comment or reply each time the form opens
  const [text, setText] = useState(() => getDraft(target, replyTo?.id));
  // The text as typed, read after a submit has been awaited
  const latestText = useRef(text);
  const [guestName, setGuestName] = useState('');
  const [spoiler, setSpoiler] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const replyName = replyTo ? commentAuthorName(replyTo) : '';
  const placeholder = replyTo
    ? t('readerComments.replyPlaceholder', { name: replyName })
    : target.kind === 'chapter'
      ? t('readerComments.placeholder', { chapter: target.chapterNumber })
      : t('comments.yourComment');
  const canPost = text.trim() !== '' && (isAuthenticated || guestName.trim() !== '') && !sending;

  const handleTextChange = (value: string) => {
    latestText.current = value;
    setText(value);
    setDraft(target, replyTo?.id, value);
  };

  // Escape closes the composer, and keeps the text as the draft
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Escape') return;
    event.preventDefault();
    onClose();
  };

  const submit = async () => {
    if (!canPost) return;
    const sent = text;
    setSending(true);
    setError(null);
    try {
      await onSubmit({
        author_name: resolveAuthorName(isAuthenticated, user, guestName.trim()),
        message: sent,
        contains_spoiler: spoiler,
        parent_id: replyTo?.id,
      });
      // Cleared only when nothing was typed while the request ran: the newer text stays as the draft
      if (latestText.current === sent) {
        setDraft(target, replyTo?.id, '');
        setText('');
        setSpoiler(false);
        setGuestName('');
      }
    } catch (err) {
      console.error('Error submitting comment:', err);
      setError(getApiErrorMessage(err, t, 'comments.submitFailed'));
    } finally {
      setSending(false);
    }
  };

  return (
    <Box>
      {replyTo && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <ReplyIcon fontSize="small" sx={{ flex: 'none', color: 'text.secondary' }} />
          <Typography variant="body2" noWrap sx={{ flex: 1, minWidth: 0, color: 'text.secondary' }}>
            {t('readerComments.replyingTo', { name: replyName })}
          </Typography>
          <IconButton size="small" onClick={onCancelReply} aria-label={t('comments.cancelReply')} sx={TOUCH_TARGET}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>
      )}

      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 1 }}>
          {error}
        </Alert>
      )}

      <TextField
        autoFocus
        multiline
        minRows={3}
        maxRows={8}
        fullWidth
        value={text}
        onChange={(event) => handleTextChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        slotProps={{ htmlInput: { 'aria-label': placeholder } }}
      />

      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1, flexWrap: 'wrap' }}>
        {!isAuthenticated && (
          <TextField
            size="small"
            label={t('readerComments.yourName')}
            value={guestName}
            onChange={(event) => setGuestName(event.target.value)}
            sx={{ flex: 1, minWidth: 120 }}
          />
        )}
        <ToggleButton
          size="small"
          value="spoiler"
          selected={spoiler}
          onChange={() => setSpoiler(!spoiler)}
          aria-label={t('comments.containsSpoilers')}
          sx={{ minHeight: TOUCH_MIN_HEIGHT, marginInlineStart: isAuthenticated ? 'auto' : 0 }}
        >
          {t('comments.markSpoiler')}
        </ToggleButton>
        <Button
          variant="contained"
          onClick={submit}
          disabled={!canPost}
          startIcon={sending ? <CircularProgress size={18} color="inherit" /> : undefined}
          sx={{ minHeight: TOUCH_MIN_HEIGHT }}
        >
          {t('readerComments.post')}
        </Button>
      </Box>
    </Box>
  );
};

// The comment composer: a pill that opens a field for a new comment or a reply
const CommentComposer = ({ target, open, replyTo, onOpen, onCancelReply, onClose, onSubmit }: CommentComposerProps) => {
  const { t } = useTranslation();
  const draft = getDraft(target);
  const pillRef = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(open);

  // Once the composer closes, focus goes back to the pill that opens it
  useEffect(() => {
    if (wasOpen.current && !open) pillRef.current?.focus({ preventScroll: true });
    wasOpen.current = open;
  }, [open]);

  return (
    <Box>
      {open ? (
        <ComposerForm
          // A change of target or of the comment replied to while open starts a fresh form, with that draft
          key={draftKey(target, replyTo?.id)}
          target={target}
          replyTo={replyTo}
          onCancelReply={onCancelReply}
          onClose={onClose}
          onSubmit={onSubmit}
        />
      ) : (
        <ButtonBase
          ref={pillRef}
          onClick={onOpen}
          sx={{
            display: 'flex',
            width: '100%',
            minHeight: TOUCH_MIN_HEIGHT,
            px: 2,
            borderRadius: '22px',
            bgcolor: 'action.hover',
            color: 'text.secondary',
            justifyContent: 'flex-start',
            textAlign: 'start',
          }}
        >
          <Typography variant="body2" component="span" noWrap sx={{ minWidth: 0 }}>
            {draft
              ? t('readerComments.draft', { text: draft })
              : target.kind === 'chapter'
                ? t('readerComments.addComment', { chapter: target.chapterNumber })
                : t('comments.addComment')}
          </Typography>
        </ButtonBase>
      )}
    </Box>
  );
};

export default CommentComposer;
