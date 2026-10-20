import React from 'react';
import { Box, Typography, Avatar, Grid, CircularProgress, Paper } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { profileService } from '@services/profile.service';
import { User } from '@models/user_types';
import { useAsync } from '@utils/useAsync';
import UserLink from './UserLink';

interface FriendsSectionProps {
    username: string;
}

const FriendsSection: React.FC<FriendsSectionProps> = ({ username }) => {
    const { t } = useTranslation();
    const { data, loading } = useAsync<User[]>(() => profileService.getUserFriends(username), [username]);
    const friends = data ?? [];

    if (loading) {
        return (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                <CircularProgress />
            </Box>
        );
    }

    if (friends.length === 0) {
        return (
            <Paper sx={{ p: 3, textAlign: 'center' }}>
                <Typography color="text.secondary">{t('friends.empty')}</Typography>
            </Paper>
        );
    }

    return (
        <Grid container spacing={2}>
            {friends.map((friend) => (
                <Grid key={friend.id} size={{ xs: 6, sm: 4, md: 3 }}>
                    <Paper sx={{ p: 2, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                        <Avatar src={friend.profile_pic || undefined} alt={friend.username} sx={{ width: 56, height: 56 }}>
                            {friend.username[0]?.toUpperCase()}
                        </Avatar>
                        <UserLink username={friend.username}>
                            <Typography variant="body2" noWrap>{friend.username}</Typography>
                        </UserLink>
                    </Paper>
                </Grid>
            ))}
        </Grid>
    );
};

export default FriendsSection;
