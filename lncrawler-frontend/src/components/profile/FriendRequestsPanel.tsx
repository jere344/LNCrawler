import React, { useEffect, useState } from 'react';
import {
    Box,
    Typography,
    Avatar,
    Tabs,
    Tab,
    Button,
    CircularProgress,
    List,
    ListItem,
    ListItemAvatar,
    ListItemText,
    ListItemSecondaryAction,
} from '@mui/material';
import CheckIcon from '@mui/icons-material/Check';
import CloseIcon from '@mui/icons-material/Close';
import { useTranslation } from 'react-i18next';
import { friendService } from '@services/friend.service';
import type { FriendRequest } from '@models/user_types';
import UserLink from './UserLink';

const FriendRequestsPanel: React.FC = () => {
    const { t } = useTranslation();
    const [direction, setDirection] = useState<'incoming' | 'outgoing'>('incoming');
    const [requests, setRequests] = useState<FriendRequest[]>([]);
    const [loading, setLoading] = useState(true);

    const load = (dir: 'incoming' | 'outgoing') => {
        setLoading(true);
        friendService
            .listRequests(dir)
            .then(setRequests)
            .catch((err) => console.error('Error loading friend requests:', err))
            .finally(() => setLoading(false));
    };

    useEffect(() => {
        load(direction);
    }, [direction]);

    const handleRespond = async (id: string, action: 'accept' | 'decline') => {
        try {
            await friendService.respond(id, action);
            load(direction);
        } catch (error) {
            console.error('Error responding to friend request:', error);
        }
    };

    return (
        <Box>
            <Typography variant="h6" gutterBottom>
                {t('friends.requests')}
            </Typography>
            <Tabs value={direction} onChange={(_, value) => setDirection(value)} sx={{ mb: 2 }}>
                <Tab value="incoming" label={t('friends.incoming')} />
                <Tab value="outgoing" label={t('friends.outgoing')} />
            </Tabs>
            {loading ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
                    <CircularProgress />
                </Box>
            ) : requests.length === 0 ? (
                <Typography color="text.secondary">{t('friends.noRequests')}</Typography>
            ) : (
                <List>
                    {requests.map((request) => {
                        const other = direction === 'incoming' ? request.requester : request.addressee;
                        return (
                            <ListItem key={request.id} divider>
                                <ListItemAvatar>
                                    <Avatar src={other.profile_pic || undefined} alt={other.username}>
                                        {other.username[0]?.toUpperCase()}
                                    </Avatar>
                                </ListItemAvatar>
                                <ListItemText primary={<UserLink username={other.username} />} />
                                {direction === 'incoming' && (
                                    <ListItemSecondaryAction>
                                        <Button
                                            size="small"
                                            startIcon={<CheckIcon />}
                                            onClick={() => handleRespond(request.id, 'accept')}
                                        >
                                            {t('friends.accept')}
                                        </Button>
                                        <Button
                                            size="small"
                                            color="error"
                                            startIcon={<CloseIcon />}
                                            onClick={() => handleRespond(request.id, 'decline')}
                                        >
                                            {t('friends.decline')}
                                        </Button>
                                    </ListItemSecondaryAction>
                                )}
                            </ListItem>
                        );
                    })}
                </List>
            )}
        </Box>
    );
};

export default FriendRequestsPanel;
