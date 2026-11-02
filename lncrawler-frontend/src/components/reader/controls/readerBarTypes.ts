// Height of the touch bottom bar (two rows), which the tablet display sheet clears
export const READER_BOTTOM_BAR_HEIGHT = 120;

// Key labels of the bound shortcuts (undefined when the key is unbound)
export interface ReaderShortcuts {
  prev?: string;
  next?: string;
  display?: string;
}

// The mark-as-read button: whether it shows, its state, and what it does
export interface MarkReadProps {
  showMarkRead: boolean;
  markReadSuccess: boolean;
  markingAsRead: boolean;
  onMarkAsRead: () => void;
}

// Props shared by the top bar, bottom bar and desktop toolbar. The reader builds them once.
export interface ReaderBarProps {
  controlsVisible: boolean;
  chapterTitle: string;
  novelTitle: string;
  hasPrev: boolean;
  hasNext: boolean;
  displayOpen: boolean;
  // Width in px kept clear at the end edge (the display panel, on phone landscape)
  reservedEnd: number;
  shortcuts: ReaderShortcuts;
  markRead: MarkReadProps;
  onHome: () => void;
  onChapterList: () => void;
  onPrevious: () => void;
  onNext: () => void;
  onDisplay: () => void;
  onListen: () => void;
  onComments: () => void;
  onSettings: () => void;
}
