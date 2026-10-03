import React from 'react';
import { Link } from 'react-router-dom';
import { SxProps, Theme } from '@mui/material';

interface UserLinkProps {
    username: string;
    children?: React.ReactNode;
    sx?: SxProps<Theme>;
}

/**
 * Renders a username as a link to that user's public profile.
 * The surrounding layout (avatar, row) stays whatever the caller renders.
 */
const UserLink: React.FC<UserLinkProps> = ({ username, children, sx }) => (
    <Link
        to={`/u/${encodeURIComponent(username)}`}
        style={{ textDecoration: 'none', color: 'inherit' }}
        onClick={(e) => e.stopPropagation()}
    >
        <span style={sx as React.CSSProperties}>{children ?? username}</span>
    </Link>
);

export default UserLink;
