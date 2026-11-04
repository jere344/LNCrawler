import { useEffect, useState } from 'react';

// False on the first render and true from the next frame on, so a panel can mount off screen and slide in
export function useEnteredOnFrame(): boolean {
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(frame);
  }, []);
  return entered;
}
