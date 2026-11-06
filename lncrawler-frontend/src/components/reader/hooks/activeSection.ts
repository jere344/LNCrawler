export interface SectionBounds { key: string; top: number; bottom: number }

// Reading line, as a fraction of the viewport height from its top
export const READING_LINE = 0.3;

// The section under the reading line: the last one whose top is at or above it; the first when all are below
export function pickActiveSection(sections: SectionBounds[], line: number): string | null {
  if (sections.length === 0) return null;
  let active = sections[0];
  for (const section of sections) {
    if (section.top <= line) active = section;
    else break;
  }
  return active.key;
}
