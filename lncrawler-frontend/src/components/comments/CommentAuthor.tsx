import { ReactNode } from 'react';
import { Avatar, Box, Typography } from '@mui/material';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import UserLink from '@components/profile/UserLink';
import { Comment } from '@models/comments_types';
import { commentAuthorName } from './commentAuthor';

interface CommentAuthorProps {
  comment: Comment;
  dense?: boolean;
  // No profile links: for a header that sits inside a button
  plain?: boolean;
  children?: ReactNode;
}

// Colors for initial-based avatars in dense mode, picked by a hash of the display name
const DENSE_AVATAR_COLORS = ['primary.main', 'secondary.main', 'success.main', 'warning.main', 'info.main'];

// Stable number for a name, so the same author always gets the same avatar color
const hashName = (name: string) => name.split('').reduce((hash, char) => (hash * 31 + char.charCodeAt(0)) >>> 0, 0);

// Avatar and name at the top of a comment, with optional extra content rendered after the name
const CommentAuthor = ({ comment, dense = false, plain = false, children }: CommentAuthorProps) => {
  const { t } = useTranslation();

  // The account's username, or the guest's name
  const displayName = commentAuthorName(comment);
  const initial = displayName ? displayName.charAt(0).toUpperCase() : '?';
  const avatarSize = dense ? 28 : 24;
  const initialColor = dense ? DENSE_AVATAR_COLORS[hashName(displayName) % DENSE_AVATAR_COLORS.length] : 'primary.main';
  // The avatar links to the profile, unless the header is plain
  const avatarLink = (username: string) => (plain ? {} : { component: Link, to: `/u/${encodeURIComponent(username)}` });

  return (
    <Box sx={{ display: 'flex', alignItems: 'center' }}>
      {/* Show avatar only if it's an authenticated user's comment and they have a profile pic */}
      {comment.user?.profile_pic && (
        <Avatar
          {...avatarLink(comment.user.username)}
          alt={displayName} // Use determined displayName
          src={comment.user.profile_pic}
          sx={{ width: avatarSize, height: avatarSize, marginInlineEnd: 1 }}
        />
      )}
      {/* Show initial-based avatar if authenticated user but no profile pic */}
      {comment.user && !comment.user.profile_pic && (
        <Avatar
          {...avatarLink(comment.user.username)}
          sx={{ width: avatarSize, height: avatarSize, marginInlineEnd: 1, bgcolor: initialColor }}>
          {initial}
        </Avatar>
      )}
      {/* Dense mode also shows an initial-based avatar for guests */}
      {dense && !comment.user && (
        <Avatar sx={{ width: avatarSize, height: avatarSize, marginInlineEnd: 1, bgcolor: initialColor }}>
          {initial}
        </Avatar>
      )}
      <Typography
        variant={dense ? 'body2' : 'subtitle1'}
        sx={dense ? { fontWeight: 600 } : { fontWeight: "bold" }}
      >
        {comment.user && !plain ? <UserLink username={comment.user.username} /> : displayName}
      </Typography>

      {!comment.user && (
        <Typography variant="caption" sx={{ marginInlineStart: 0.5, color: "text.secondary" }}>
          {t('comments.guest')}
        </Typography>
      )}

      {children}
    </Box>
  );
};

export default CommentAuthor;
