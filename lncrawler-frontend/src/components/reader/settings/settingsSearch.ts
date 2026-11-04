// Plain text for matching: accents and case do not count
export const normaliseSearchText = (text: string) =>
  text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

interface SearchableSetting {
  label: string;
  keywords: string;
  // Page name, matched like the keywords
  page: string;
}

// Every word must match the label, the keywords or the page name. Label matches rank first:
// starting with the query, then containing it. Equal ranks keep the index order.
export const searchSettings = <T extends SearchableSetting>(query: string, items: T[]): T[] => {
  const phrase = normaliseSearchText(query.trim());
  if (!phrase) return [];
  const words = phrase.split(/\s+/);

  return items
    .map((item, index) => {
      const label = normaliseSearchText(item.label);
      const haystack = normaliseSearchText(`${item.keywords} ${item.page}`);
      const matches = words.every((word) => label.includes(word) || haystack.includes(word));
      const rank = label.startsWith(phrase) ? 0 : label.includes(phrase) ? 1 : 2;
      return { item, index, rank, matches };
    })
    .filter(({ matches }) => matches)
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map(({ item }) => item);
};

// A label split around the matching text, for highlighting. Null when the label has no plain match.
export const splitAtMatch = (label: string, query: string) => {
  const phrase = normaliseSearchText(query.trim());
  const normalised = normaliseSearchText(label);
  const start = phrase ? normalised.indexOf(phrase) : -1;
  // Decomposed accents or odd case changes shift the positions, so no highlight then
  if (start < 0 || normalised.length !== label.length) return null;
  return {
    before: label.slice(0, start),
    match: label.slice(start, start + phrase.length),
    after: label.slice(start + phrase.length),
  };
};
