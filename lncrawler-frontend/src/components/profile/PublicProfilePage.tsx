import React, { useEffect, useState } from 'react';
import {
    Box,
    Typography,
    Avatar,
    Paper,
    Tabs,
    Tab,
    Button,
    CircularProgress,
    Divider,
    Chip,
    Alert,
    Grid,
} from '@mui/material';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { profileService } from '@services/profile.service';
import type { PublicProfile } from '@models/user_types';
import type { ReadingList } from '@models/readinglist_types';
import type { Comment } from '@models/comments_types';
import type { Review } from '@services/review.service';
import { useAuth } from '@context/AuthContext';
import FriendButton from './FriendButton';
import FriendsTab from './FriendsTab';
import { BaseNovelCard } from '@components/common/novelcardtypes/BaseNovelCard';
import { getNovelSourceLink } from '@utils/Misc';
import ReadingListCard from '@components/readinglist/ReadingListCard';
import OverviewReviewsSection from '@components/common/reviews/OverviewReviewsSection';
import PublicLibraryTab from '@components/library/PublicLibraryTab';

// Social fields hold handles/pseudos, not URLs. Map the ones with a known
// profile URL shape so the chip links out; others render as plain text.
const SOCIAL_URLS: Record<string, (handle: string) => string | undefined> = {
    mal: (h) => `https://myanimelist.net/profile/${encodeURIComponent(h)}`,
    anilist: (h) => `https://anilist.co/user/${encodeURIComponent(h)}`,
    novelupdates: (h) => `https://www.novelupdates.com/user/${encodeURIComponent(h)}/`,
    website: (h) => (/^https?:\/\//i.test(h) ? h : undefined),
};

const PublicProfilePage: React.FC = () => {
    const { username = '' } = useParams<{ username: string }>();
    const { t } = useTranslation();
    const navigate = useNavigate();
    const { user } = useAuth();

    const [profile, setProfile] = useState<PublicProfile | null>(null);
    const [loading, setLoading] = useState(true);
    const [tab, setTab] = useState(0);

    useEffect(() => {
        let active = true;
        setProfile(null);
        setTab(0);
        setLoading(true);
        profileService
            .getPublicProfile(username)
            .then((data) => active && setProfile(data))
            .catch((err) => {
                console.error('Error loading profile:', err);
                if (active) setProfile(null);
            })
            .finally(() => active && setLoading(false));
        return () => {
            active = false;
        };
    }, [username]);

    if (loading) {
        return (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
                <CircularProgress />
            </Box>
        );
    }

    if (!profile) {
        return <Alert severity="error">{t('profile.notFound')}</Alert>;
    }

    const isOwner = user?.username === profile.username;
    const canSee = (section: string) => {
        if (isOwner) return true;
        const visibility = profile.visibility[section as keyof typeof profile.visibility];
        if (visibility === 'public') return true;
        if (visibility === 'friends') return profile.friendship_status === 'friends';
        return false;
    };

    const tabs = [
        { key: 'overview', label: t('profile.tabs.overview'), visible: true },
        { key: 'library', label: t('profile.tabs.library'), visible: canSee('library') },
        { key: 'reading_lists', label: t('profile.tabs.readingLists'), visible: canSee('reading_lists') },
        { key: 'reviews', label: t('profile.tabs.reviews'), visible: canSee('reviews') },
        { key: 'comments', label: t('profile.tabs.comments'), visible: canSee('comments') },
        { key: 'friends', label: t('profile.tabs.friends'), visible: canSee('friends') },
    ].filter((item) => item.visible);

    return (
        <Box>
            <Paper sx={{ overflow: 'hidden', mb: 3 }}>
                <Box
                    sx={{
                        height: { xs: 120, sm: 200 },
                        backgroundColor: 'primary.dark',
                        backgroundImage: profile.banner ? `url(${profile.banner})` : undefined,
                        backgroundSize: 'cover',
                        backgroundPosition: 'center',
                    }}
                />
                <Box sx={{ px: 3, pb: 3, display: 'flex', gap: 3, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                    <Avatar
                        src={profile.profile_pic || undefined}
                        alt={profile.username}
                        sx={{ width: 120, height: 120, mt: -6, border: '4px solid', borderColor: 'background.paper' }}
                    >
                        {profile.username[0]?.toUpperCase()}
                    </Avatar>
                    <Box sx={{ flex: 1, minWidth: 200, pt: 2 }}>
                        <Typography variant="h5">{profile.username}</Typography>
                        <Typography variant="body2" color="text.secondary">
                            {t('profile.memberSinceFull', { date: new Date(profile.date_joined).toLocaleDateString() })}
                        </Typography>
                        {profile.bio && <Typography sx={{ mt: 1 }}>{profile.bio}</Typography>}
                        {profile.social_links && Object.keys(profile.social_links).length > 0 && (
                            <Box sx={{ mt: 1, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                                {Object.entries(profile.social_links).map(([key, value]) => {
                                    const handle = String(value).trim();
                                    const href = /^https?:\/\//i.test(handle)
                                        ? handle
                                        : SOCIAL_URLS[key as keyof typeof SOCIAL_URLS]?.(handle);
                                    return (
                                        <Chip
                                            key={key}
                                            label={`${t(`profile.social.${key}`)}: ${handle}`}
                                            {...(href
                                                ? { component: 'a', href, target: '_blank', rel: 'noopener noreferrer', clickable: true }
                                                : {})}
                                            size="small"
                                        />
                                    );
                                })}
                            </Box>
                        )}
                    </Box>
                    <Box>
                        {isOwner ? (
                            <Button variant="outlined" onClick={() => navigate('/settings')}>
                                {t('header.settings')}
                            </Button>
                        ) : (
                            <FriendButton
                                username={profile.username}
                                initialStatus={profile.friendship_status}
                                onStatusChange={(status) => setProfile({ ...profile, friendship_status: status })}
                            />
                        )}
                    </Box>
                </Box>
            </Paper>

            <Tabs value={tab} onChange={(_, value) => setTab(value)} variant="scrollable" scrollButtons="auto" sx={{ mb: 3 }}>
                {tabs.map((item) => (
                    <Tab key={item.key} label={item.label} />
                ))}
            </Tabs>

            {tabs[tab]?.key === 'overview' && <OverviewTab profile={profile} />}
            {tabs[tab]?.key === 'library' && (
                <PublicLibraryTab
                    username={profile.username}
                    showNotes={canSee('library_notes')}
                    showRatings={canSee('library_ratings')}
                />
            )}
            {tabs[tab]?.key === 'reading_lists' && <ReadingListsTab username={profile.username} />}
            {tabs[tab]?.key === 'reviews' && <ReviewsTab username={profile.username} />}
            {tabs[tab]?.key === 'comments' && <CommentsTab username={profile.username} />}
            {tabs[tab]?.key === 'friends' && <FriendsTab username={profile.username} />}
        </Box>
    );
};

const OverviewTab: React.FC<{ profile: PublicProfile }> = ({ profile }) => {
    const { t } = useTranslation();
    const hasGatedContent =
        profile.stats ||
        profile.currently_reading ||
        (profile.top_genres && profile.top_genres.length > 0) ||
        (profile.recent_reads && profile.recent_reads.length > 0);
    return (
        <Box>
            {!hasGatedContent && profile.pinned_novels.length === 0 && (
                <Alert severity="info" sx={{ mb: 3 }}>{t('profile.privateSection')}</Alert>
            )}
            {profile.stats && (
                <Paper sx={{ p: 3, mb: 3 }}>
                    <Typography variant="h6" gutterBottom>
                        {t('profile.about')}
                    </Typography>
                    <Grid container spacing={2}>
                        <Grid size={{ xs: 6, md: 3 }}>
                            <Typography variant="h5">{profile.stats.word_read.toLocaleString()}</Typography>
                            <Typography variant="body2" color="text.secondary">{t('profile.wordsRead')}</Typography>
                        </Grid>
                        <Grid size={{ xs: 6, md: 3 }}>
                            <Typography variant="h5">{profile.stats.chapters_read_count}</Typography>
                            <Typography variant="body2" color="text.secondary">{t('profile.chaptersRead')}</Typography>
                        </Grid>
                        <Grid size={{ xs: 6, md: 3 }}>
                            <Typography variant="h5">{profile.stats.novels_count}</Typography>
                            <Typography variant="body2" color="text.secondary">{t('profile.novelsInLibrary')}</Typography>
                        </Grid>
                    </Grid>
                </Paper>
            )}

            {profile.currently_reading && (
                <Paper sx={{ p: 3, mb: 3 }}>
                    <Typography variant="h6" gutterBottom>{t('profile.currentlyReading')}</Typography>
                    <Typography>{profile.currently_reading.novel.title}</Typography>
                    {profile.currently_reading.last_read_at && (
                        <Typography variant="body2" color="text.secondary">
                            {t('profile.lastRead', { date: new Date(profile.currently_reading.last_read_at).toLocaleDateString() })}
                        </Typography>
                    )}
                </Paper>
            )}

            {profile.top_genres && profile.top_genres.length > 0 && (
                <Paper sx={{ p: 3, mb: 3 }}>
                    <Typography variant="h6" gutterBottom>{t('profile.topGenres')}</Typography>
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                        {profile.top_genres.map((genre) => (
                            <Chip key={genre.name} label={`${genre.name} (${genre.count})`} />
                        ))}
                    </Box>
                </Paper>
            )}

            {profile.pinned_novels.length > 0 && (
                <Box sx={{ mb: 3 }}>
                    <Typography variant="h6" gutterBottom>{t('profile.pinnedNovels')}</Typography>
                    <Grid container spacing={2}>
                        {profile.pinned_novels.map((novel) => (
                            <Grid key={novel.id} size={{ xs: 6, sm: 4, md: 3, lg: 2 }}>
                                <BaseNovelCard novel={novel} hideUserState {...getNovelSourceLink(novel)} />
                            </Grid>
                        ))}
                    </Grid>
                </Box>
            )}

            {profile.recent_reads && profile.recent_reads.length > 0 && (
                <Box>
                    <Typography variant="h6" gutterBottom>{t('profile.recentReads')}</Typography>
                    <Grid container spacing={2}>
                        {profile.recent_reads.map((read) => (
                            <Grid key={read.novel.id} size={{ xs: 6, sm: 4, md: 3, lg: 2 }}>
                                <BaseNovelCard novel={read.novel} hideUserState {...getNovelSourceLink(read.novel)} />
                            </Grid>
                        ))}
                    </Grid>
                </Box>
            )}
        </Box>
    );
};

const ReadingListsTab: React.FC<{ username: string }> = ({ username }) => {
    const { t } = useTranslation();
    const [lists, setLists] = useState<ReadingList[]>([]);
    const [loading, setLoading] = useState(true);
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);

    useEffect(() => {
        let active = true;
        setLoading(true);
        profileService
            .getUserReadingLists(username, page)
            .then((data) => {
                if (!active) return;
                setLists(data.results);
                setTotalPages(data.total_pages);
            })
            .catch((err) => console.error('Error loading reading lists:', err))
            .finally(() => active && setLoading(false));
        return () => {
            active = false;
        };
    }, [username, page]);

    if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>;
    if (lists.length === 0) return <Alert severity="info">{t('profile.emptySection')}</Alert>;

    return (
        <Box>
            <Grid container spacing={2}>
                {lists.map((list) => (
                    <Grid key={list.id} size={{ xs: 12, sm: 6, md: 4 }}>
                        <ReadingListCard list={list} />
                    </Grid>
                ))}
            </Grid>
            <Pagination page={page} totalPages={totalPages} onChange={setPage} />
        </Box>
    );
};

const ReviewsTab: React.FC<{ username: string }> = ({ username }) => {
    const { t } = useTranslation();
    const [reviews, setReviews] = useState<Review[]>([]);
    const [loading, setLoading] = useState(true);
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);

    useEffect(() => {
        let active = true;
        setLoading(true);
        profileService
            .getUserReviews(username, page)
            .then((data) => {
                if (!active) return;
                setReviews(data.reviews);
                setTotalPages(data.pagination.total_pages);
            })
            .catch((err) => console.error('Error loading reviews:', err))
            .finally(() => active && setLoading(false));
        return () => {
            active = false;
        };
    }, [username, page]);

    if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>;
    if (reviews.length === 0) return <Alert severity="info">{t('profile.emptySection')}</Alert>;

    return (
        <Box>
            <OverviewReviewsSection reviews={reviews} isLoading={loading} />
            <Pagination page={page} totalPages={totalPages} onChange={setPage} />
        </Box>
    );
};

const commentTargetPath = (comment: Comment): string | null => {
    if (comment.target_type === 'novel' && comment.target_slug) {
        return `/novels/${comment.target_slug}`;
    }
    if (comment.target_type === 'chapter' && comment.target_novel_slug && comment.target_source_slug) {
        return `/novels/${comment.target_novel_slug}/${comment.target_source_slug}/chapter/${comment.target_chapter_number}`;
    }
    if (comment.target_type === 'board' && comment.target_slug) {
        return `/boards/${comment.target_slug}`;
    }
    return null;
};

const CommentMessage: React.FC<{ comment: Comment }> = ({ comment }) => {
    const { t } = useTranslation();
    const [revealed, setRevealed] = useState(false);

    if (!comment.contains_spoiler) {
        return <Typography sx={{ mt: 1 }}>{comment.message}</Typography>;
    }

    return (
        <Box sx={{ mt: 1 }}>
            <Typography
                onClick={() => setRevealed((value) => !value)}
                sx={{
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    filter: revealed ? 'none' : 'blur(5px)',
                    cursor: 'pointer',
                    transition: 'filter 0.2s',
                    p: 1,
                }}
            >
                {comment.message}
            </Typography>
            {!revealed && (
                <Typography
                    variant="caption"
                    sx={{ color: 'warning.main', display: 'block', mt: 0.5, fontStyle: 'italic' }}
                >
                    {t('comments.spoiler')}
                </Typography>
            )}
        </Box>
    );
};

const CommentsTab: React.FC<{ username: string }> = ({ username }) => {
    const { t } = useTranslation();
    const [comments, setComments] = useState<Comment[]>([]);
    const [loading, setLoading] = useState(true);
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);

    useEffect(() => {
        let active = true;
        setLoading(true);
        profileService
            .getUserComments(username, page)
            .then((data) => {
                if (!active) return;
                setComments(data.results);
                setTotalPages(data.total_pages);
            })
            .catch((err) => console.error('Error loading comments:', err))
            .finally(() => active && setLoading(false));
        return () => {
            active = false;
        };
    }, [username, page]);

    if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>;
    if (comments.length === 0) return <Alert severity="info">{t('profile.emptySection')}</Alert>;

    return (
        <Box>
            <Grid container spacing={2}>
                {comments.map((comment) => {
                    const targetPath = commentTargetPath(comment);
                    return (
                        <Grid key={comment.id} size={12}>
                            <Paper sx={{ p: 2 }}>
                                <Typography variant="body2" color="text.secondary">
                                    {targetPath ? (
                                        <Link to={targetPath}>
                                            {comment.target_title || t('profile.commentOn')}
                                        </Link>
                                    ) : (
                                        comment.target_title || t('profile.commentOn')
                                    )}
                                </Typography>
                                <CommentMessage comment={comment} />
                            </Paper>
                        </Grid>
                    );
                })}
            </Grid>
            <Pagination page={page} totalPages={totalPages} onChange={setPage} />
        </Box>
    );
};

const Pagination: React.FC<{ page: number; totalPages: number; onChange: (page: number) => void }> = ({ page, totalPages, onChange }) => {
    if (totalPages <= 1) return null;
    return (
        <>
            <Divider sx={{ my: 3 }} />
            <Box sx={{ display: 'flex', justifyContent: 'center', gap: 1, alignItems: 'center' }}>
                <Button disabled={page <= 1} onClick={() => onChange(page - 1)}>
                    Prev
                </Button>
                <Typography>
                    {page} / {totalPages}
                </Typography>
                <Button disabled={page >= totalPages} onClick={() => onChange(page + 1)}>
                    Next
                </Button>
            </Box>
        </>
    );
};

export default PublicProfilePage;
