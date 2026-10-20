import { useCallback, useEffect, useState, type DependencyList } from 'react';

// Runs `fn` whenever `deps` change. A response that arrives after its inputs
// changed is dropped, so a slow request cannot overwrite newer data.
// `data` keeps the last successful result; `error` is set on failure and
// cleared at the start of each run.
export function useAsync<T>(fn: () => Promise<T>, deps: DependencyList) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [runId, setRunId] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fn()
      .then((result) => {
        if (active) setData(result);
      })
      .catch((err) => {
        console.error(err);
        if (active) setError(err ?? new Error('Request failed'));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- callers list their inputs in deps
  }, [...deps, runId]);

  const reload = useCallback(() => setRunId((n) => n + 1), []);

  return { data, loading, error, reload, setData };
}
