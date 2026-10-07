import React, { useState } from 'react';
import { Button, CircularProgress } from '@mui/material';
import PersonAddIcon from '@mui/icons-material/PersonAdd';
import PersonRemoveIcon from '@mui/icons-material/PersonRemove';
import CheckIcon from '@mui/icons-material/Check';
import { useTranslation } from 'react-i18next';
import { friendService } from '@services/friend.service';
import { useAuth } from '@context/AuthContext';
import type { FriendshipStatus } from '@models/user_types';

interface FriendButtonProps {
    username: string;
    initialStatus: FriendshipStatus;
    onStatusChange?: (status: FriendshipStatus) => void;
}

const FriendButton: React.FC<FriendButtonProps> = ({ username, initialStatus, onStatusChange }) => {
    const { t } = useTranslation();
    const { isAuthenticated } = useAuth();
    const [status, setStatus] = useState<FriendshipStatus>(initialStatus);
    const [loading, setLoading] = useState(false);

    const update = (next: FriendshipStatus) => {
        setStatus(next);
        onStatusChange?.(next);
    };

    const handleClick = async () => {
        setLoading(true);
        try {
            if (status === 'none') {
                const result = await friendService.sendRequest(username);
                update(result.status === 'accepted' ? 'friends' : 'request_sent');
            } else if (status === 'friends' || status === 'request_sent') {
                await friendService.removeFriend(username);
                update('none');
            } else if (status === 'request_received') {
                // Accepting requires the request id; fetch the pending request.
                const requests = await friendService.listRequests('incoming');
                const request = requests.find((r) => r.requester.username === username);
                if (request) {
                    await friendService.respond(request.id, 'accept');
                    update('friends');
                }
            }
        } catch (error) {
            console.error('Friend action failed:', error);
        } finally {
            setLoading(false);
        }
    };

    if (!isAuthenticated || status === 'self') return null;

    const config: Record<Exclude<FriendshipStatus, 'self'>, { label: string; icon: React.ReactNode; variant: 'contained' | 'outlined' | 'text' }> = {
        none: { label: t('friends.addFriend'), icon: <PersonAddIcon />, variant: 'contained' },
        request_sent: { label: t('friends.requestSent'), icon: <PersonRemoveIcon />, variant: 'outlined' },
        request_received: { label: t('friends.acceptRequest'), icon: <CheckIcon />, variant: 'contained' },
        friends: { label: t('friends.unfriend'), icon: <PersonRemoveIcon />, variant: 'outlined' },
    };
    const { label, icon, variant } = config[status];

    return (
        <Button variant={variant} startIcon={loading ? <CircularProgress size={16} /> : icon} onClick={handleClick} disabled={loading}>
            {label}
        </Button>
    );
};

export default FriendButton;
