import React, { useState, useEffect } from 'react';
import {
  Box,
  IconButton,
  Tooltip,
  Typography,
  Chip,
  useTheme,
} from '@mui/material';
import { reviewService, ReviewReaction } from '@services/review.service';

interface ReviewReactionsProps {
  reviewId: string;
  reactions: ReviewReaction[];
  currentUserReaction: ReviewReaction | null;
}

const REACTION_EMOJIS: Record<string, string> = {
  sparkle: '✨',
  heart: '❤️',
  laugh: '😂',
  eyebrow: '🤨',
  lightbulb: '💡',
  write: '📝',
  paint: '🎨',
  sick: '🤢',
};

const REACTION_LABELS: Record<string, string> = {
  sparkle: 'Nice',
  heart: 'Love it',
  laugh: 'Funny',
  eyebrow: 'Confusing',
  lightbulb: 'Informative',
  write: 'Well written',
  paint: 'Creative',
  sick: 'Disgusting',
};

const ReviewReactions: React.FC<ReviewReactionsProps> = ({
  reviewId,
  reactions: initialReactions,
  currentUserReaction: initialUserReaction
}) => {
  const theme = useTheme();
  const [loading, setLoading] = useState<string | null>(null);
  const [reactions, setReactions] = useState<ReviewReaction[]>(initialReactions);
  const [currentUserReaction, setCurrentUserReaction] = useState<ReviewReaction | null>(initialUserReaction);

  // Update local state when props change
  useEffect(() => {
    setReactions(initialReactions);
    setCurrentUserReaction(initialUserReaction);
  }, [initialReactions, initialUserReaction]);

  // Group reactions by type and count
  const reactionCounts = reactions.reduce((acc, reaction) => {
    acc[reaction.reaction] = (acc[reaction.reaction] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  // Sort reaction types by count (descending), then alphabetically
  const sortedReactionEntries = Object.entries(REACTION_EMOJIS).sort(([keyA, _], [keyB, __]) => {
    const countA = reactionCounts[keyA] || 0;
    const countB = reactionCounts[keyB] || 0;
    
    if (countA !== countB) {
      return countB - countA; // Sort by count descending
    }
    return keyA.localeCompare(keyB); // Sort alphabetically if counts are equal
  });

  const handleReactionClick = async (reactionType: string) => {
    if (loading) return;
    
    setLoading(reactionType);
    
    try {
      const isCurrentReaction = currentUserReaction?.reaction === reactionType;
      
      if (isCurrentReaction) {
        // Remove reaction - optimistically update UI
        const reactionToRemove = currentUserReaction;
        setCurrentUserReaction(null);
        setReactions(prev => prev.filter(r => 
          !(r.id === reactionToRemove?.id && r.reaction === reactionToRemove?.reaction)
        ));
        
        // Make API call
        await reviewService.removeReaction(reviewId);
      } else {
        // Store the previous reaction if it exists
        const previousReaction = currentUserReaction;
        
        // Create a temporary ID for optimistic updates
        const tempReaction: ReviewReaction = {
          id: `temp-${Date.now()}`,
          reaction: reactionType
        };
        
        // Remove previous reaction if it exists
        let updatedReactions = previousReaction 
          ? reactions.filter(r => r.id !== previousReaction.id)
          : [...reactions];
        
        // Add new reaction
        updatedReactions.push(tempReaction);
        
        // Update local state
        setCurrentUserReaction(tempReaction);
        setReactions(updatedReactions);
        
        // Make API call
        await reviewService.addReaction(reviewId, reactionType);
      }

    } catch (error) {
      console.error('Error handling reaction:', error);
      // Revert to original state on error
      setReactions(initialReactions);
      setCurrentUserReaction(initialUserReaction);
    } finally {
      setLoading(null);
    }
  };

  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="subtitle2" gutterBottom>
        Reactions
      </Typography>
      
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
        {sortedReactionEntries.map(([key, emoji]) => {
          const count = reactionCounts[key] || 0;
          const isActive = currentUserReaction?.reaction === key;
          
          return (
            <Tooltip key={key} title={REACTION_LABELS[key]}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <IconButton
                  size="small"
                  onClick={() => handleReactionClick(key)}
                  disabled={loading === key}
                  sx={{
                    fontSize: '1.2rem',
                    bgcolor: isActive ? theme.palette.primary.light : 'transparent',
                    '&:hover': {
                      bgcolor: theme.palette.action.hover,
                    },
                  }}
                >
                  {emoji}
                </IconButton>
                {count > 0 && (
                  <Chip
                    label={count}
                    size="small"
                    variant="outlined"
                    sx={{ ml: 0.5, height: 20, fontSize: '0.75rem' }}
                  />
                )}
              </Box>
            </Tooltip>
          );
        })}
      </Box>
    </Box>
  );
};

export default ReviewReactions;
