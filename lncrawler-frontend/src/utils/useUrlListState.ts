import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useDebounce } from '@utils/useDebounce';

type UrlParamUpdates = Record<string, string | null | undefined>;

// Reads and writes list state (filters, sort, search, page) in the URL, so
// back/forward and shared links restore the same view.
// Empty, null or undefined values remove the param.
export function useUrlListState() {
  const [searchParams, setSearchParams] = useSearchParams();

  const setParams = useCallback(
    (updates: UrlParamUpdates, options?: { replace?: boolean }) => {
      const next = new URLSearchParams(searchParams);
      for (const [key, value] of Object.entries(updates)) {
        if (value) next.set(key, value);
        else next.delete(key);
      }
      setSearchParams(next, options);
    },
    [searchParams, setSearchParams]
  );

  return { searchParams, setParams };
}

// Text input mirrored to a URL param. The input stays local so typing is
// responsive, the debounced value is written to the URL (the loader or effect
// reacts to it), and URL changes such as back/forward update the input.
export function useUrlSearch(param: string = 'q') {
  const { searchParams, setParams } = useUrlListState();
  const urlValue = searchParams.get(param) || '';
  const [value, setValue] = useState(urlValue);
  const debouncedValue = useDebounce(value);

  // Mirror the debounced search into the URL and reset paging.
  useEffect(() => {
    if (debouncedValue === urlValue) return;
    setParams({ [param]: debouncedValue, page: null }, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only react to the debounced value
  }, [debouncedValue]);

  // Keep the input in sync when the URL changes (back/forward or another source).
  useEffect(() => {
    setValue(urlValue);
  }, [urlValue]);

  return [value, setValue] as const;
}
