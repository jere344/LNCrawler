import { useEffect } from 'react';

const REVEAL_ZONE_PX = 48; // Height of the top strip that brings the desktop toolbar back

// Desktop: moving the pointer to the top edge shows the hidden toolbar
export function useRevealOnTopHover(enabled: boolean, onReveal: () => void) {
  useEffect(() => {
    if (!enabled) return;
    const handleMouseMove = (e: MouseEvent) => {
      if (e.clientY < REVEAL_ZONE_PX) onReveal();
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, [enabled, onReveal]);
}
