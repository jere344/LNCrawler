import { useEffect, useState } from 'react';

const DEBOUNCE_TIME = 300;

export function useDebounce<T>(value: T, delay: number = DEBOUNCE_TIME): T {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}
