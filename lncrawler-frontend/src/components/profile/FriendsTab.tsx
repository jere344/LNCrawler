import React, { useEffect, useState } from 'react';
import {
    Box,
    Typography,
    TextField,
    Autocomplete,
    Button,
    CircularProgress,
    Divider,
} from '@mui/material';
import PersonAddIcon from '@mui/icons-material/PersonAdd';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@context/AuthContext';
import { readingListService } from '@services/readinglist.service';
import { friendService } from '@services/friend.service';
import { User } from '@models/user_types';
import FriendRequestsPanel from './FriendRequestsPanel';
import FriendsSection from './FriendsSection';

interface FriendsTabProps {
    username: string;
}

const FriendsTab: React.FC<FriendsTabProps> = ({ username }) => {
    const { t } = useTranslation();
    const { user } = useAuth();
    const isOwner = user?.username === username;

    const [options, setOptions] = useState<User[]>([]);
    const [search, setSearch] = useState('');
    const [selected, setSelected] = useState<User | null>(null);
    const [sending, setSending] = useState(false);

    useEffect(() => {
        if (!isOwner || search.trim().length < 2) {
            setOptions([]);
            return;
        }
        const handle = setTimeout(() => {
            readingListService
                .searchUsers(search.trim())
                .then(setOptions)
                .catch((err) => {
                    console.error('Error searching users:', err);
                    setOptions([]);
                });
        }, 300);
        return () => clearTimeout(handle);
    }, [search, isOwner]);

    const handleSend = async (selected: User | null) => {
        if (!selected) return;
        setSending(true);
        try {
            await friendService.sendRequest(selected.username);
            setSearch('');
            setSelected(null);
            setOptions([]);
        } catch (err) {
            console.error('Error sending friend request:', err);
        } finally {
            setSending(false);
        }
    };

    return (
        <Box>
            {isOwner && (
                <>
                    <Typography variant="h6" gutterBottom>
                        {t('friends.addFriend')}
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mb: 2 }}>
                        <Autocomplete
                            fullWidth
                            size="small"
                            options={options}
                            getOptionLabel={(option) => option.username}
                            isOptionEqualToValue={(option, value) => option.id === value.id}
                            value={selected}
                            inputValue={search}
                            onInputChange={(_, value) => setSearch(value)}
                            onChange={(_, value) => setSelected(value)}
                            renderInput={(params) => (
                                <TextField {...params} label={t('friends.searchUsers')} />
                            )}
                        />
                        <Button
                            variant="contained"
                            size="small"
                            startIcon={sending ? <CircularProgress size={16} /> : <PersonAddIcon />}
                            disabled={!selected || sending}
                            onClick={() => handleSend(selected)}
                            sx={{ whiteSpace: 'nowrap', flexShrink: 0 }}
                        >
                            {t('friends.sendRequest')}
                        </Button>
                    </Box>
                    <Divider sx={{ my: 2 }} />
                    <FriendRequestsPanel />
                    <Divider sx={{ my: 2 }} />
                </>
            )}
            <Typography variant="h6" gutterBottom>
                {t('friends.heading')}
            </Typography>
            <FriendsSection username={username} />
        </Box>
    );
};

export default FriendsTab;
