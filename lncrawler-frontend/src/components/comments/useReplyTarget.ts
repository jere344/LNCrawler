import { useEffect, useState } from 'react';
import type { Comment } from '@models/comments_types';

// The comment the composer replies to. It is cleared once the composer is closed, so the next comment starts as a new one.
export function useReplyTarget(composing: boolean) {
  const [replyTo, setReplyTo] = useState<Comment | null>(null);

  // The composer's reply target goes once the composer is closed
  useEffect(() => {
    if (!composing) setReplyTo(null);
  }, [composing]);

  return { replyTo, setReplyTo };
}
