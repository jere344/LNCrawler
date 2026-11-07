/** Sets the lock screen handler of each action (null clears it). Actions the browser does not support are skipped. */
export function setMediaSessionHandlers(handlers: [MediaSessionAction, MediaSessionActionHandler | null][]): void {
  handlers.forEach(([action, handler]) => {
    try {
      navigator.mediaSession.setActionHandler(action, handler);
    } catch {
      // this browser does not support the action
    }
  });
}

/** The lock screen state for an app status: 'playing' and 'paused' as themselves, anything else as 'none'. */
export function playbackStateOf(status: string): MediaSessionPlaybackState {
  return status === 'playing' ? 'playing' : status === 'paused' ? 'paused' : 'none';
}
