import React, { useState } from 'react';
import {
    Box,
    Typography,
    TextField,
    Autocomplete,
    Avatar,
    Chip,
    Alert,
    CircularProgress,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import BookIcon from '@mui/icons-material/Book';
import { useTranslation } from 'react-i18next';
import { novelService } from '@services/novel.service';
import { profileService } from '@services/profile.service';
import type { Novel } from '@models/novels_types';

const MAX_PINNED = 6;

interface PinnedNovelsPickerProps {
    pinnedNovels: Novel[];
    onChange: (novels: Novel[]) => void;
}

const PinnedNovelsPicker: React.FC<PinnedNovelsPickerProps> = ({ pinnedNovels, onChange }) => {
    const { t } = useTranslation();
    const [options, setOptions] = useState<Novel[]>([]);
    const [searching, setSearching] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const search = async (query: string) => {
        if (query.length < 2) {
            setOptions([]);
            return;
        }
        setSearching(true);
        try {
            const data = await novelService.searchNovels({ query, page_size: 20 });
            setOptions(data.results || []);
        } catch (err) {
            console.error('Error searching novels:', err);
        } finally {
            setSearching(false);
        }
    };

    const handleAdd = async (novel: Novel | null) => {
        if (!novel) return;
        if (pinnedNovels.some((item) => item.id === novel.id)) return;
        setError(null);
        try {
            await profileService.pinNovel(novel.id);
            onChange([...pinnedNovels, novel]);
        } catch (err) {
            console.error('Error pinning novel:', err);
            setError(t('profile.pinError'));
        }
    };

    const handleRemove = async (novel: Novel) => {
        try {
            await profileService.unpinNovel(novel.id);
            onChange(pinnedNovels.filter((item) => item.id !== novel.id));
        } catch (err) {
            console.error('Error unpinning novel:', err);
        }
    };

    return (
        <Box>
            <Typography variant="h6" gutterBottom>
                {t('profile.pinnedNovels')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                {t('profile.pinnedHint', { max: MAX_PINNED })}
            </Typography>
            {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}

            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 2 }}>
                {pinnedNovels.map((novel) => (
                    <Chip
                        key={novel.id}
                        avatar={
                            <Avatar src={novel.prefered_source?.cover_min_url || undefined}>
                                <BookIcon fontSize="small" />
                            </Avatar>
                        }
                        label={novel.title}
                        onDelete={() => handleRemove(novel)}
                        deleteIcon={<CloseIcon />}
                    />
                ))}
            </Box>

            {pinnedNovels.length < MAX_PINNED && (
                <Autocomplete
                    options={options.filter((option) => !pinnedNovels.some((pinned) => pinned.id === option.id))}
                    getOptionLabel={(option) => option.title}
                    loading={searching}
                    onChange={(_, value) => {
                        handleAdd(value);
                    }}
                    onInputChange={(_, value) => search(value)}
                    renderInput={(params) => (
                        <TextField
                            {...params}
                            label={t('profile.searchNovel')}
                            slotProps={{
                                ...params.slotProps,
                                input: {
                                    ...params.slotProps.input,
                                    endAdornment: (
                                        <>
                                            {searching ? <CircularProgress size={16} /> : null}
                                            {params.slotProps.input.endAdornment}
                                        </>
                                    ),
                                },
                            }}
                        />
                    )}
                />
            )}
        </Box>
    );
};

export default PinnedNovelsPicker;
