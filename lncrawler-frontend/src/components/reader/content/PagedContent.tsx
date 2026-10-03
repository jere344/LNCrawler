import React, { useEffect, useLayoutEffect, useRef, useState, useCallback } from 'react';
import { Box } from '@mui/material';
import { ChapterContent } from '@models/novels_types';
import { ReaderSettings } from '../ReaderSettings';
import ReaderContent from './ReaderContent';

export interface PagedContentRef {
  goToNextPage: () => boolean;
  goToPrevPage: () => boolean;
  goToPage: (page: number) => void;
  getProgress: () => number;
  readonly currentPage: number;
  readonly totalPages: number;
}

interface PagedContentProps {
  chapter: ChapterContent;
  settings: ReaderSettings;
  initialProgress?: number;
  onPageChange?: (currentPage: number, totalPages: number) => void;
  ref?: React.Ref<PagedContentRef>;
}

const PagedContent: React.FC<PagedContentProps> = ({
  chapter,
  settings,
  initialProgress = 0,
  onPageChange,
  ref,
}) => {
  const outerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  const [, setPage] = useState(0);
  const [, setTotal] = useState(1);

  const pageRef = useRef(0);
  const totalRef = useRef(1);
  const didRestoreRef = useRef(false);
  const initialProgressRef = useRef(initialProgress);
  const onPageChangeRef = useRef(onPageChange);

  useEffect(() => {
    onPageChangeRef.current = onPageChange;
  }, [onPageChange]);

  const applyPage = useCallback((next: number, totalPages: number) => {
    const clamped = Math.min(Math.max(next, 0), Math.max(totalPages - 1, 0));
    const changed = clamped !== pageRef.current || totalPages !== totalRef.current;
    pageRef.current = clamped;
    totalRef.current = totalPages;
    setPage(clamped);
    setTotal(totalPages);
    const el = contentRef.current;
    if (el) {
      el.style.transform = `translateX(${-clamped * el.clientWidth}px)`;
    }
    if (changed) {
      onPageChangeRef.current?.(clamped + 1, totalPages);
    }
  }, []);

  // Measure the columns and (re)place the current page.
  // On the first pass we restore `initialProgress`; every later pass (resize,
  // rotation, font change) keeps the same fraction of the chapter visible.
  const reflow = useCallback(() => {
    const el = contentRef.current;
    if (!el) return;
    const pageWidth = el.clientWidth;
    if (pageWidth <= 0) return;

    el.style.columnWidth = `${pageWidth}px`;
    el.style.columnGap = '0px';

    const oldTotal = totalRef.current;
    let progress: number;
    if (!didRestoreRef.current) {
      progress = initialProgressRef.current;
      didRestoreRef.current = true;
    } else {
      progress = oldTotal <= 1 ? 0 : (pageRef.current / (oldTotal - 1)) * 100;
    }

    const totalPages = Math.max(1, Math.round(el.scrollWidth / pageWidth));
    const target = totalPages <= 1 ? 0 : Math.round((progress / 100) * (totalPages - 1));
    applyPage(target, totalPages);
  }, [applyPage]);

  useLayoutEffect(() => {
    reflow();

    let raf = 0;
    const schedule = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(reflow);
    };

    window.addEventListener('resize', schedule);
    window.addEventListener('orientationchange', schedule);

    const observer = new ResizeObserver(schedule);
    if (outerRef.current) observer.observe(outerRef.current);

    if (document.fonts?.ready) {
      document.fonts.ready.then(reflow).catch(() => undefined);
    }

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', schedule);
      window.removeEventListener('orientationchange', schedule);
      observer.disconnect();
    };
  }, [reflow]);

  // Re-flow when typography settings change (preserves reading position).
  useEffect(() => {
    reflow();
  }, [
    reflow,
    settings.fontSize,
    settings.lineSpacing,
    settings.wordSpacing,
    settings.letterSpacing,
    settings.fontFamily,
    settings.textAlign,
    settings.paragraphIndent,
    settings.paragraphSpacing,
    settings.margin,
  ]);

  // Images load after the first measurement and change the column layout.
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const images = Array.from(el.querySelectorAll('img'));
    const onLoad = () => reflow();
    images.forEach(img => {
      if (!img.complete) img.addEventListener('load', onLoad);
    });
    return () => images.forEach(img => img.removeEventListener('load', onLoad));
  }, [reflow, chapter.body]);

  const goToPage = useCallback((page: number) => {
    applyPage(page, totalRef.current);
  }, [applyPage]);

  React.useImperativeHandle(ref, () => ({
    goToNextPage: () => {
      if (pageRef.current < totalRef.current - 1) {
        applyPage(pageRef.current + 1, totalRef.current);
        return true;
      }
      return false;
    },
    goToPrevPage: () => {
      if (pageRef.current > 0) {
        applyPage(pageRef.current - 1, totalRef.current);
        return true;
      }
      return false;
    },
    goToPage,
    getProgress: () => (totalRef.current <= 1 ? 0 : (pageRef.current / (totalRef.current - 1)) * 100),
    get currentPage() {
      return pageRef.current;
    },
    get totalPages() {
      return totalRef.current;
    },
  }));

  return (
    <Box
      ref={outerRef}
      sx={{
        position: 'absolute',
        inset: 0,
        overflow: 'hidden',
        px: `${settings.margin}%`,
      }}
    >
      <Box
        ref={contentRef}
        sx={{
          height: '100%',
          columnFill: 'auto',
        }}
      >
        <ReaderContent chapter={chapter} settings={settings} />
      </Box>
    </Box>
  );
};

export default PagedContent;
