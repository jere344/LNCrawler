import { useState, useEffect, useRef } from 'react';
import {
  Box,
  Paper,
  Typography,
  Avatar,
  Button,
  IconButton,
  TextField,
  Checkbox,
  FormControlLabel,
  CircularProgress,
  Alert,
  Tooltip,
  alpha,
} from '@mui/material';
import ReplyIcon from '@mui/icons-material/Reply';
import CloseIcon from '@mui/icons-material/Close';
import { chatService } from '../../services/chat.service';
import { type ApiError } from '../../services/api';
import { ChatMessage } from '@models/chat_types';
import { formatDateTime } from '@utils/Misc';
import { useAuth } from '../../context/AuthContext';
import { useTranslation } from 'react-i18next';

const PAGE_SIZE = 100;
// ponytail: cap quote lookups so a click can't fetch unbounded history; raise if chains get deep.
const MAX_QUOTE_LOOKUP_PAGES = 10;

interface NewMessage {
  author_name: string;
  message: string;
  contains_spoiler: boolean;
}

const dedupById = (list: ChatMessage[]): ChatMessage[] => {
  const seen = new Set<string>();
  return list.filter((m) => (seen.has(m.id) ? false : (seen.add(m.id), true)));
};

interface ChatRowProps {
  message: ChatMessage;
  isOwn: boolean;
  highlight: boolean;
  onReply: (message: ChatMessage) => void;
  onQuoteClick: (parentId: string) => void;
}

const ChatRow = ({ message, isOwn, highlight, onReply, onQuoteClick }: ChatRowProps) => {
  const { t, i18n } = useTranslation();
  const [spoilerRevealed, setSpoilerRevealed] = useState(false);
  const displayName =
    message.user?.username && message.user.username.length > 0
      ? message.user.username
      : message.author_name;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', mb: 1 }}>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 0.5,
          mb: 0.25,
          justifyContent: 'flex-start',
          flexDirection: isOwn ? 'row-reverse' : 'row',
        }}
      >
        {!isOwn &&
          (message.user?.profile_pic ? (
            <Avatar alt={displayName} src={message.user.profile_pic} sx={{ width: 18, height: 18 }} />
          ) : (
            <Avatar sx={{ width: 18, height: 18, bgcolor: 'primary.main', fontSize: '0.65rem' }}>
              {displayName ? displayName.charAt(0).toUpperCase() : '?'}
            </Avatar>
          ))}
        {!isOwn && (
          <Typography variant="caption" sx={{ fontWeight: 600 }}>
            {displayName}
          </Typography>
        )}
        {!isOwn && !message.user && (
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            {t('comments.guest')}
          </Typography>
        )}
        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
          {formatDateTime(message.created_at, i18n.language)}
          {message.edited && ` (${t('comments.edited')})`}
        </Typography>
      </Box>

      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 0.5,
          justifyContent: 'flex-start',
          flexDirection: isOwn ? 'row-reverse' : 'row',
        }}
      >
        <Paper
          id={`chat-msg-${message.id}`}
          elevation={0}
          sx={{
            px: 1.25,
            py: 0.75,
            maxWidth: '82%',
            borderRadius: 2,
            bgcolor: isOwn ? 'primary.main' : 'action.hover',
            color: isOwn ? 'primary.contrastText' : 'text.primary',
            scrollMarginTop: 80,
            transition: 'box-shadow 0.3s',
            ...(highlight && {
              boxShadow: (theme) => `0 0 0 2px ${theme.palette.primary.main}`,
            }),
          }}
        >
          {message.parent && (
            <Box
              onClick={() => onQuoteClick(message.parent!.id)}
              sx={{
                mb: 0.5,
                px: 0.75,
                py: 0.25,
                borderLeft: '3px solid',
                borderColor: isOwn ? 'primary.contrastText' : 'primary.main',
                bgcolor: isOwn
                  ? (theme) => alpha(theme.palette.primary.contrastText, 0.15)
                  : 'background.default',
                borderRadius: 0.5,
                cursor: 'pointer',
                '&:hover': { opacity: 0.85 },
              }}
            >
              <Typography
                variant="caption"
                sx={{
                  display: 'block',
                  color: isOwn ? 'primary.contrastText' : 'text.secondary',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {message.parent.author_name}: {message.parent.message}
              </Typography>
            </Box>
          )}

          {message.contains_spoiler ? (
            <Box
              sx={{
                px: 0.5,
                mx: -0.25,
                borderRadius: 0.5,
                bgcolor: isOwn ? 'rgba(0,0,0,0.18)' : 'rgba(0,0,0,0.06)',
              }}
            >
              <Typography
                variant="body2"
                onClick={() => setSpoilerRevealed(!spoilerRevealed)}
                sx={{
                  color: isOwn ? 'primary.contrastText' : 'text.primary',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  filter: spoilerRevealed ? 'none' : 'blur(5px)',
                  cursor: 'pointer',
                  transition: 'filter 0.2s',
                }}
              >
                {message.message}
              </Typography>
              {!spoilerRevealed && (
                <Typography variant="caption" sx={{ color: 'warning.main', fontStyle: 'italic' }}>
                  {t('comments.spoiler')}
                </Typography>
              )}
            </Box>
          ) : (
            <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
              {message.message}
            </Typography>
          )}
        </Paper>

        <Tooltip title={t('comments.reply')}>
          <IconButton
            size="small"
            onClick={() => onReply(message)}
            sx={{ color: 'text.secondary', flexShrink: 0 }}
          >
            <ReplyIcon sx={{ fontSize: 16 }} />
          </IconButton>
        </Tooltip>
      </Box>
    </Box>
  );
};

interface ChatComposerProps {
  replyTo: ChatMessage | null;
  onCancelReply: () => void;
  onSubmit: (data: NewMessage) => Promise<void>;
}

const ChatComposer = ({ replyTo, onCancelReply, onSubmit }: ChatComposerProps) => {
  const { isAuthenticated, user } = useAuth();
  const { t } = useTranslation();
  const [authorName, setAuthorName] = useState('');
  const [message, setMessage] = useState('');
  const [containsSpoiler, setContainsSpoiler] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setAuthorName(isAuthenticated && user ? user.username : '');
  }, [isAuthenticated, user]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isAuthenticated && !authorName.trim()) {
      setError(t('comments.enterName'));
      return;
    }
    if (!message.trim()) {
      setError(t('comments.enterComment'));
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit({
        author_name: isAuthenticated && user ? user.username : authorName,
        message,
        contains_spoiler: containsSpoiler,
      });
      setMessage('');
      setContainsSpoiler(false);
    } catch (err) {
      console.error('Error submitting chat message:', err);
      const apiErr = err as ApiError;
      setError(apiErr?.response?.data?.error || t('comments.submitFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Paper elevation={2} sx={{ p: 1, borderRadius: 2 }}>
      {error && (
        <Alert severity="error" sx={{ mb: 1, py: 0 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {replyTo && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5, px: 0.5 }}>
          <Typography variant="caption" sx={{ color: 'text.secondary', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {t('comments.replyTo', { author: replyTo.user?.username || replyTo.author_name })}
          </Typography>
          <IconButton size="small" onClick={onCancelReply}>
            <CloseIcon sx={{ fontSize: 16 }} />
          </IconButton>
        </Box>
      )}

      <Box component="form" onSubmit={handleSubmit} noValidate sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
        {!isAuthenticated && (
          <TextField
            size="small"
            label={t('comments.yourName')}
            value={authorName}
            onChange={(e) => setAuthorName(e.target.value)}
            sx={{ width: 140, flexShrink: 0 }}
          />
        )}
        <TextField
          size="small"
          fullWidth
          multiline
          maxRows={4}
          placeholder={replyTo ? t('comments.yourReply') : t('comments.yourComment')}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
        />
        <Button type="submit" variant="contained" disabled={submitting} sx={{ flexShrink: 0, height: 40 }}>
          {submitting ? t('comments.posting') : replyTo ? t('comments.postReply') : t('comments.postComment')}
        </Button>
      </Box>

      <FormControlLabel
        control={
          <Checkbox
            size="small"
            checked={containsSpoiler}
            onChange={(e) => setContainsSpoiler(e.target.checked)}
            color="primary"
          />
        }
        label={<Typography variant="caption">{t('comments.containsSpoilers')}</Typography>}
        sx={{ mt: 0.5, ml: 0 }}
      />
    </Paper>
  );
};

const ChatPage = () => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [page, setPage] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [replyTo, setReplyTo] = useState<ChatMessage | null>(null);
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const data = await chatService.listChat(1, PAGE_SIZE);
        if (!active) return;
        setMessages(data.results);
        setPage(data.current_page);
        setTotalPages(Math.max(1, data.total_pages));
      } catch (err) {
        console.error('Failed to fetch chat:', err);
        if (active) setError(t('chat.loadFailed'));
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only
  }, []);

  const loadMore = async () => {
    if (loadingMore || page >= totalPages) return;
    setLoadingMore(true);
    try {
      const data = await chatService.listChat(page + 1, PAGE_SIZE);
      setMessages((prev) => dedupById([...prev, ...data.results]));
      setPage(data.current_page);
      setTotalPages(Math.max(1, data.total_pages));
    } catch (err) {
      console.error('Failed to fetch more chat:', err);
    } finally {
      setLoadingMore(false);
    }
  };

  const handleScroll = (event: React.UIEvent<HTMLDivElement>) => {
    const el = event.currentTarget;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 200) {
      void loadMore();
    }
  };

  const focusMessage = (id: string): boolean => {
    const el = document.getElementById(`chat-msg-${id}`);
    if (!el) return false;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setHighlightId(id);
    window.setTimeout(() => setHighlightId(null), 2000);
    return true;
  };

  const loadUntilFound = async (id: string) => {
    let acc: ChatMessage[] = [];
    let nextPage = page + 1;
    let found = false;
    setLoadingMore(true);
    try {
      while (!found && nextPage <= totalPages && nextPage <= page + MAX_QUOTE_LOOKUP_PAGES) {
        const data = await chatService.listChat(nextPage, PAGE_SIZE);
        acc = acc.concat(data.results);
        found = acc.some((m) => m.id === id);
        nextPage += 1;
      }
    } catch (err) {
      console.error('Failed to load quoted message:', err);
    } finally {
      setLoadingMore(false);
    }
    if (acc.length > 0) {
      setMessages((prev) => dedupById([...prev, ...acc]));
      setPage(nextPage - 1);
    }
    if (found) {
      window.setTimeout(() => focusMessage(id), 80);
    } else if (nextPage <= totalPages) {
      // stopped early because of the lookup cap while pages remain
      setNotice(t('chat.quoteLookupLimit'));
    } else {
      setNotice(t('chat.quoteUnavailable'));
    }
  };

  const handleQuoteClick = (parentId: string) => {
    if (!focusMessage(parentId)) void loadUntilFound(parentId);
  };

  const prependMessage = (created: ChatMessage) => {
    setMessages((prev) => dedupById([created, ...prev]));
    scrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
    setReplyTo(null);
  };

  const handleSubmitMessage = async (data: NewMessage) => {
    const created = await chatService.addChatMessage(
      replyTo ? { ...data, parent_id: replyTo.id } : data
    );
    prependMessage(created);
  };

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: { xs: 'calc(100vh - 200px)', md: 'calc(100vh - 180px)' },
        minHeight: 420,
        py: 1,
      }}
    >
      <Typography variant="h6" sx={{ mb: 1 }}>
        {t('chat.title')}
      </Typography>

      {notice && (
        <Alert severity="info" onClose={() => setNotice(null)} sx={{ mb: 1, py: 0 }}>
          {notice}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', flex: 1 }}>
          <CircularProgress />
        </Box>
      ) : error ? (
        <Alert severity="error" sx={{ my: 2 }}>
          {error}
        </Alert>
      ) : (
        <Box
          ref={scrollRef}
          onScroll={handleScroll}
          sx={{
            flex: 1,
            minHeight: 0,
            overflowY: 'auto',
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1,
            p: 1,
          }}
        >
          {messages.length === 0 ? (
            <Typography color="text.secondary" sx={{ textAlign: 'center', py: 4 }}>
              {t('chat.noMessages')}
            </Typography>
          ) : (
            messages.map((message) => (
              <ChatRow
                key={message.id}
                message={message}
                isOwn={!!user && !!message.user && message.user.username === user.username}
                highlight={highlightId === message.id}
                onReply={setReplyTo}
                onQuoteClick={handleQuoteClick}
              />
            ))
          )}
          {loadingMore && (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
              <CircularProgress size={24} />
            </Box>
          )}
        </Box>
      )}

      {!loading && !error && (
        <Box sx={{ pt: 1 }}>
          <ChatComposer replyTo={replyTo} onCancelReply={() => setReplyTo(null)} onSubmit={handleSubmitMessage} />
        </Box>
      )}
    </Box>
  );
};

export default ChatPage;
