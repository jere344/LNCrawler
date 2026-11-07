import { useEffect, useState } from 'react';
import { novelService } from '@services/novel.service';

export interface AutocompleteOption {
  name: string;
  count: number;
}

// Suggestions for a tag or author input. Pass a debounced value so each keystroke
// does not hit the endpoint. An empty input clears the list.
export function useAutocomplete(kind: 'tag' | 'author', input: string) {
  const [options, setOptions] = useState<AutocompleteOption[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (input.length < 1) {
      setOptions([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    novelService
      .getAutocompleteSuggestions(kind, input)
      .then((response) => { if (!cancelled) setOptions(response); })
      .catch((error) => {
        console.error(`Error fetching ${kind} suggestions:`, error);
        if (!cancelled) setOptions([]);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [kind, input]);

  return { options, loading };
}
