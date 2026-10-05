import { useState, useEffect, useRef } from 'react';
import {
  Box,
  Paper,
  Typography,
  Avatar,
  Button,
  CircularProgress,
  Alert,
} from '@mui/material';
import ReplyIcon from '@mui/icons-material/Reply';
import { alpha } from '@mui/material/styles';
import CommentForm from '@components/comments/CommentForm';
import { chatService } from '../../services/chat.service';
import { ChatMessage } from '@models/chat_types';
import { CommentFormData } from '@models/comments_types';
import { formatDateTime } from '@utils/Misc';
import { useTranslation } from 'react-i18next';

const PAGE_SIZE = 100;
// ponytail: cap quote lookups so a click can't fetch unbounded history; raise if chains get deep.
const MAX_QUOTE_LOOKUP_PAGES = 10;

const dedupById = (list: ChatMessage[]): ChatMessage[] => {
  const seen = new Set<string>();
  return list.filter((m) => (seen.has(m.id) ? false : (seen.add(m.id), true)));
};

interface ChatRowProps {
  message: ChatMessage;
  highlight: boolean;
  isReplying: boolean;
  onReplyToggle: (message: ChatMessage | null) => void;
  onQuoteClick: (parentId: string) => void;
  onAddReply: (data: CommentFormData, parent: ChatMessage) => Promise<void>;
}

const ChatRow = ({
  message,
  highlight,
  isReplying,
  onReplyToggle,
  onQuoteClick,
  onAddReply,
}: ChatRowProps) => {
  const { t, i18n } = useTranslation();
  const [spoilerRevealed, setSpoilerRevealed] = useState(false);
  const displayName =
    message.user?.username && message.user.username.length > 0
      ? message.user.username
      : message.author_name;

  return (
    <Box sx={{ mb: 1.5 }}>
      <Paper
        id={`chat-msg-${message.id}`}
        elevation={1}
        sx={{
          p: 1.5,
          scrollMarginTop: 80,
          transition: 'box-shadow 0.3s, background-color 0.3s',
          ...(highlight && {
            boxShadow: (theme) => `0 0 0 2px ${theme.palette.primary.main}`,
            backgroundColor: (theme) => alpha(theme.palette.primary.main, 0.08),
          }),
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
          {message.user?.profile_pic ? (
            <Avatar alt={displayName} src={message.user.profile_pic} sx={{ width: 22, height: 22, mr: 1 }} />
          ) : (
            <Avatar sx={{ width: 22, height: 22, mr: 1, bgcolor: 'primary.main', fontSize: '0.75rem' }}>
              {displayName ? displayName.charAt(0).toUpperCase() : '?'}
            </Avatar>
          )}
          <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
            {displayName}
          </Typography>
          <Typography variant="caption" sx={{ color: 'text.secondary', ml: 1 }}>
            {formatDateTime(message.created_at, i18n.language)}
            {message.edited && ` (${t('comments.edited')})`}
          </Typography>
        </Box>

        {message.parent && (
          <Box
            onClick={() => onQuoteClick(message.parent!.id)}
            sx={{
              display: 'flex',
              gap: 0.5,
              mb: 0.5,
              px: 1,
              py: 0.5,
              borderLeft: '3px solid',
              borderColor: 'primary.main',
              bgcolor: 'action.hover',
              borderRadius: 0.5,
              cursor: 'pointer',
              '&:hover': { bgcolor: 'action.selected' },
            }}
          >
            <Typography variant="body2" sx={{ color: 'primary.main', fontWeight: 'bold' }}>
              ||
            </Typography>
            <Typography
              variant="body2"
              sx={{ color: 'text.secondary', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            >
              {message.parent.author_name}: {message.parent.message}
            </Typography>
          </Box>
        )}

        {message.contains_spoiler ? (
          <Box>
            <Typography
              variant="body2"
              onClick={() => setSpoilerRevealed(!spoilerRevealed)}
              sx={{
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

        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 0.5 }}>
          <Button
            size="small"
            variant="text"
            startIcon={<ReplyIcon fontSize="small" />}
            onClick={() => onReplyToggle(isReplying ? null : message)}
          >
            {isReplying ? t('comments.cancelReply') : t('comments.reply')}
          </Button>
        </Box>
      </Paper>

      {isReplying && (
        <Box sx={{ ml: 4, mt: 1 }}>
          <CommentForm
            isReply
            parentAuthor={displayName}
            onSubmit={(data) => onAddReply(data, message)}
            onCancel={() => onReplyToggle(null)}
          />
        </Box>
      )}
    </Box>
  );
};

const ChatPage = () => {
  const { t } = useTranslation();
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

  const handleAddMessage = async (data: CommentFormData) => {
    const created = await chatService.addChatMessage(data);
    prependMessage(created);
  };

  const handleAddReply = async (data: CommentFormData, parent: ChatMessage) => {
    const created = await chatService.addChatMessage({ ...data, parent_id: parent.id });
    prependMessage(created);
  };

  return (
    <Box sx={{ py: 1 }}>
      <Typography variant="h5" gutterBottom>
        {t('chat.title')}
      </Typography>

      <CommentForm onSubmit={handleAddMessage} />

      {notice && (
        <Alert severity="info" onClose={() => setNotice(null)} sx={{ my: 2 }}>
          {notice}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
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
            mt: 2,
            height: { xs: 'calc(100vh - 320px)', md: 'calc(100vh - 300px)' },
            minHeight: 360,
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
                highlight={highlightId === message.id}
                isReplying={replyTo?.id === message.id}
                onReplyToggle={setReplyTo}
                onQuoteClick={handleQuoteClick}
                onAddReply={handleAddReply}
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
    </Box>
  );
};

export default ChatPage;
