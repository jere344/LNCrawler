import { useState, useEffect, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { novelService } from '../../../services/api';
import { userService } from '@services/user.service';
import { useNotification } from '@context/NotificationContext';
import { NovelFromSource as ISourceDetail, NovelDetail as INovelDetail, Novel as INovel } from '@models/novels_types';

export type NovelRatingState = { avg_rating: number | null, rating_count: number, user_rating: number | null };

export function useSourceDetail(novelSlug: string | undefined, sourceSlug: string | undefined) {
  const { t } = useTranslation();
  const { notify } = useNotification();
  const location = useLocation();
  const linkState = location.state as { novel?: INovel; source?: ISourceDetail | null } | null;

  // Metadata already fetched by the list card that navigated here. Only trust
  // it when it matches the URL, since the card link may point to the source the
  // user has a reading history on rather than the preferred source.
  const getPrefetchedSource = useCallback((): ISourceDetail | null => {
    if (!novelSlug || !sourceSlug) return null;
    const s = linkState?.source;
    if (s && s.source_slug === sourceSlug && s.novel_slug === novelSlug) return s;
    const n = linkState?.novel;
    if (n && n.slug === novelSlug) {
      return [n.reading_source, n.prefered_source].find(
        (cand) => cand?.source_slug === sourceSlug && cand?.novel_slug === novelSlug
      ) ?? null;
    }
    return null;
  }, [linkState, novelSlug, sourceSlug]);

  const [source, setSource] = useState<ISourceDetail | null>(getPrefetchedSource);
  const [novel, setNovel] = useState<INovelDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [votingInProgress, setVotingInProgress] = useState<boolean>(false);
  const [novelRating, setNovelRating] = useState<NovelRatingState>(() => ({
    avg_rating: linkState?.novel?.avg_rating ?? null,
    rating_count: linkState?.novel?.rating_count ?? 0,
    user_rating: null
  }));
  const [isBookmarked, setIsBookmarked] = useState(false);
  const [bookmarking, setBookmarking] = useState(false);

  useEffect(() => {
    if (novel) setIsBookmarked(!!novel.is_bookmarked);
  }, [novel]);

  useEffect(() => {
    const fetchSourceDetail = async () => {
      if (!novelSlug || !sourceSlug) return;

      const prefetched = getPrefetchedSource();
      setSource(prefetched);
      setLoading(true);
      setError(null);

      try {
        // The source response embeds the novel detail, so the page no longer
        // needs a second request.
        const data = await novelService.getSourceDetail(novelSlug, sourceSlug);
        setSource(data);
        setNovel(data.novel);
        setNovelRating({
          avg_rating: data.novel.avg_rating,
          rating_count: data.novel.rating_count,
          user_rating: data.novel.user_rating
        });
      } catch (err) {
        console.error('Error fetching source details:', err);
        if (!prefetched) {
          setError(t('sourceDetail.loadFailed'));
        }
      }

      setLoading(false);
    };

    fetchSourceDetail();
  }, [novelSlug, sourceSlug, getPrefetchedSource, t]);

  const handleVote = async (voteType: 'up' | 'down') => {
    if (!novelSlug || !sourceSlug || votingInProgress || !source) return;
    
    setVotingInProgress(true);
    try {
      const voteResponse = await novelService.voteSource(novelSlug, sourceSlug, voteType);
      setSource({
        ...source,
        upvotes: voteResponse.upvotes,
        downvotes: voteResponse.downvotes,
        vote_score: voteResponse.vote_score,
        user_vote: voteResponse.user_vote
      });
    } catch (err) {
      console.error('Error voting for source:', err);
    } finally {
      setVotingInProgress(false);
    }
  };

  const handleToggleBookmark = async () => {
    if (!novelSlug || bookmarking) return;
    setBookmarking(true);
    try {
      if (isBookmarked) {
        await userService.removeNovelBookmark(novelSlug);
        setIsBookmarked(false);
      } else {
        await userService.addNovelBookmark(novelSlug);
        setIsBookmarked(true);
      }
    } catch (err) {
      console.error('Error toggling bookmark:', err);
    } finally {
      setBookmarking(false);
    }
  };

  const handleShare = () => {
    if (navigator.share) {
      navigator.share({
        title: source?.title || t('common.share'),
        url: window.location.href,
      }).catch((error) => console.log('Error sharing:', error));
    } else {
      navigator.clipboard.writeText(window.location.href)
        .then(() => notify({ message: t('readingLists.linkCopied'), severity: 'success' }))
        .catch((error) => console.error('Error copying link:', error));
    }
  };

  return { source, setSource, novel, loading, error, novelRating, isBookmarked, bookmarking, votingInProgress, handleVote, handleToggleBookmark, handleShare };
}
