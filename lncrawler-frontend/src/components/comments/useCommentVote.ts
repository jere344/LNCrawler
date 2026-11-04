import { useState } from 'react';
import { commentService } from '@services/comment.service';
import { Comment } from '@models/comments_types';

// Vote counts and the current user's vote on a comment, with the action to vote
// `onVoted` receives the comment with the new counts and vote, so a parent can keep it
export const useCommentVote = (comment: Comment, onVoted?: (comment: Comment) => void) => {
  const [votes, setVotes] = useState({ upvotes: comment.upvotes, downvotes: comment.downvotes });
  const [currentVote, setCurrentVote] = useState<'up' | 'down' | null>(comment.user_vote || null);
  const [isVoting, setIsVoting] = useState(false);

  const vote = async (voteType: 'up' | 'down') => {
    if (isVoting) return;
    setIsVoting(true);
    try {
      const updatedCommentData = await commentService.voteComment(comment.id, voteType);
      setVotes({
        upvotes: updatedCommentData.upvotes,
        downvotes: updatedCommentData.downvotes,
      });
      setCurrentVote(voteType);
      onVoted?.({
        ...comment,
        upvotes: updatedCommentData.upvotes,
        downvotes: updatedCommentData.downvotes,
        user_vote: voteType,
      });
    } catch (error) {
      console.error('Failed to vote on comment:', error);
    } finally {
      setIsVoting(false);
    }
  };

  return {
    upvotes: votes.upvotes,
    downvotes: votes.downvotes,
    currentVote,
    isVoting,
    vote,
  };
};

export type CommentVote = ReturnType<typeof useCommentVote>;
