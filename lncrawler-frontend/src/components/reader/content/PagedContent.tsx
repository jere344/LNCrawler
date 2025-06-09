import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { Box, IconButton, Typography, Slider } from '@mui/material';
import { KeyboardArrowLeft, KeyboardArrowRight, Lock, LockOpen } from '@mui/icons-material';
import { ChapterContent } from '@models/novels_types';
import { ReaderSettings } from '../ReaderSettings';
import ReaderContent from './ReaderContent';

interface PagedContentRef {
  goToNextPage: () => boolean;
  goToPrevPage: () => boolean;
  goToPage?: (page: number) => void;
  currentPage: number;
}

interface PagedContentProps {
  chapter: ChapterContent;
  settings: ReaderSettings;
  onPageChange?: (currentPage: number, totalPages: number) => void;
  isScrollLocked?: boolean;
  onScrollLockChange?: (locked: boolean) => void;
  ref?: React.Ref<PagedContentRef>;
  saveScrollPosition: () => void;
}

const PagedContent: React.FC<PagedContentProps> = ({ 
  chapter, 
  settings, 
  onPageChange,
  isScrollLocked = false,
  onScrollLockChange,
    saveScrollPosition,
  ref
}) => {
  const [currentPage, setCurrentPage] = useState(0);
  const [pages, setPages] = useState<string[]>([]);
  const [internalScrollLock, setInternalScrollLock] = useState(isScrollLocked);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Sync internal state with prop
  useEffect(() => {
    setInternalScrollLock(isScrollLocked);
  }, [isScrollLocked]);

  // Split content into pages based on viewport height
  const calculatePages = useCallback(() => {
    if (!chapter.body) return [];
    
    // Create the main container for measurements
    const container = document.createElement('div');
    container.style.position = 'absolute';
    container.style.visibility = 'hidden';
    container.style.zIndex = '-1000';
    
    // Apply the same styles as the actual reading container
    const containerClientWidth = containerRef.current?.clientWidth;
    container.style.width = (containerClientWidth && containerClientWidth > 0 ? containerClientWidth : 800) + 'px';
    container.style.fontSize = `${settings.fontSize}px`;
    container.style.lineHeight = settings.lineSpacing.toString();
    container.style.fontFamily = settings.fontFamily || 'inherit';
    container.innerHTML = chapter.body.replace(/src="images\//g, `src="${chapter.images_path}/`);
    
    // Append to body to get accurate measurements
    document.body.appendChild(container);
    
    // The height we want for each page
    const viewportHeight = window.innerHeight * 0.85;
    const pages: string[] = [];
    
    // Get all child nodes to keep exact structure including text nodes
    const allElements = Array.from(container.childNodes);
    
    // Clone container for testing content fits
    const testContainer = document.createElement('div');
    testContainer.style.width = container.style.width;
    testContainer.style.fontSize = container.style.fontSize;
    testContainer.style.lineHeight = container.style.lineHeight;
    testContainer.style.fontFamily = container.style.fontFamily;
    
    let currentPage = document.createElement('div');
    
    // Process each element
    for (let i = 0; i < allElements.length; i++) {
      const element = allElements[i].cloneNode(true) as HTMLElement;
      
      // Try adding this element to the current page
      currentPage.appendChild(element);
      testContainer.innerHTML = '';
      testContainer.appendChild(currentPage.cloneNode(true));
      document.body.appendChild(testContainer);
      
      // Check if adding this element exceeds the desired height
      if (testContainer.offsetHeight > viewportHeight) {
        // If this is a text node or small element, try to split it
        if (element.nodeType === Node.TEXT_NODE || 
            (element.offsetHeight < viewportHeight * 0.5 && 
             !['IMG', 'FIGURE', 'TABLE'].includes(element.tagName || ''))) {
          
          // Remove the element that made it too big
          currentPage.removeChild(currentPage.lastChild as Node);
          
          // Save current page if it has content
          if (currentPage.innerHTML.trim()) {
            pages.push(currentPage.innerHTML);
          }
          
          // Create new page with this element
          currentPage = document.createElement('div');
          currentPage.appendChild(element);
        } else {
          // This is a large element (like an image) that doesn't fit
          
          // If current page has other content, save it first
          if (currentPage.childNodes.length > 1) {
            // Remove the element that made it too big
            currentPage.removeChild(currentPage.lastChild as Node);
            
            // Save the current page without this element
            pages.push(currentPage.innerHTML);
            
            // Start a new page with just this element
            currentPage = document.createElement('div');
            currentPage.appendChild(element);
          }
          
          // Element is too big for a single page but it's the only element
          // We'll keep it as its own page and let it scroll if necessary
        }
      }
      
      // Check if we've reached the end
      if (i === allElements.length - 1 && currentPage.innerHTML.trim()) {
        pages.push(currentPage.innerHTML);
      }
      
      document.body.removeChild(testContainer);
    }
    
    // Clean up
    document.body.removeChild(container);
    
    return pages.length > 0 ? pages : [chapter.body];
  }, [chapter.body, chapter.images_path, settings]);

  // Single debounced function for both settings changes and resize
  const debouncedRecalculatePages = useCallback(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    
    debounceTimerRef.current = setTimeout(() => {
      const newPages = calculatePages();
      setPages(newPages);
      setCurrentPage(0);
    }, currentPage === 0 ? 0 : 500); // Shorter delay if already on first page
  }, [calculatePages]);

  // Update pages when content or settings change
  useEffect(() => {
    debouncedRecalculatePages();
  }, [debouncedRecalculatePages]);

  // Update pages on resize with same debounced function
  useEffect(() => {
    const handleResize = () => {
      debouncedRecalculatePages();
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [debouncedRecalculatePages]);

  // Clean up debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  // Notify parent of page changes
  useEffect(() => {
    if (onPageChange) {
      onPageChange(currentPage + 1, pages.length);
    }
    saveScrollPosition();
  }, [currentPage, pages.length, onPageChange]);

  const goToNextPage = () => {
    if (currentPage < pages.length - 1) {
      setCurrentPage(prev => prev + 1);
      return true;
    }
    return false;
  };

  const goToPrevPage = () => {
    if (currentPage > 0) {
      setCurrentPage(prev => prev - 1);
      return true;
    }
    return false;
  };

  const goToPage = (page: number) => {
    if (page >= 0 && page < pages.length) {
      setCurrentPage(page);
    }
  };

  // Expose navigation methods to parent using useImperativeHandle
  React.useImperativeHandle(ref, () => ({
    goToNextPage,
    goToPrevPage,
    goToPage,
    currentPage: currentPage,
  }));

  const currentPageChapter = useMemo(() => ({
    ...chapter,
    body: pages[currentPage] || ''
  }), [chapter, pages, currentPage]);

  // Handle scroll lock with target specificity
  useEffect(() => {
    // Create a function that checks if the event target is within the settings drawer
    const isInSettingsDrawer = (target: EventTarget | null) => {
      if (!target) return false;
      
      // Check if the target or its parents have the 'reader-settings-drawer' class
      let element = target as HTMLElement;
      while (element && element !== document.body) {
        if (element.classList.contains('reader-settings-drawer')) {
          return true;
        }
        element = element.parentElement as HTMLElement;
      }
      return false;
    };

    // Prevent scroll only if not in settings drawer
    const preventScroll = (e: Event) => {
      if (internalScrollLock && !isInSettingsDrawer(e.target)) {
        e.preventDefault();
      }
    };

    if (internalScrollLock) {
      document.addEventListener('wheel', preventScroll, { passive: false });
      document.addEventListener('touchmove', preventScroll, { passive: false });
      document.body.classList.add('reading-scroll-locked');
    } else {
      document.body.classList.remove('reading-scroll-locked');
    }

    return () => {
      document.removeEventListener('wheel', preventScroll);
      document.removeEventListener('touchmove', preventScroll);
      document.body.classList.remove('reading-scroll-locked');
    };
  }, [internalScrollLock]);

  // Handler for toggle scroll lock
  const toggleScrollLock = () => {
    const newLockState = !internalScrollLock;
    
    setInternalScrollLock(newLockState);
    
    // Notify parent component if callback provided
    if (onScrollLockChange) {
      onScrollLockChange(newLockState);
    }
  };


  useEffect(() => {
    // Scroll to ensure the container is visible
    if (containerRef.current) {
        // Calculate container's position relative to the viewport
        const containerRect = containerRef.current.getBoundingClientRect();
        
        // If the container is not fully in view, scroll to it
        if (containerRect.top < 0 || containerRect.bottom > window.innerHeight) {
            // Custom scrolling to account for 20px fixed header
            const scrollPosition = window.pageYOffset + containerRect.top - 20; // Subtract 20px for the header
            window.scrollTo({
            top: scrollPosition,
            behavior: 'instant'
            });
            return;
        }
    }
  }, [currentPage, pages]);

  return (
    <Box ref={containerRef} sx={{ position: 'relative', minHeight: '60vh' }}>
      {/* Scroll Lock Button */}
      <IconButton
        onClick={(e) => {
          e.stopPropagation();
          toggleScrollLock();
        }}
        sx={{
          position: 'absolute',
          top: 8,
          right: 8,
          zIndex: 10,
          backgroundColor: 'rgba(0, 0, 0, 0.1)',
          color: settings.fontColor || 'inherit',
          opacity: 0.7,
          transition: 'opacity 0.3s ease',
          '&:hover': {
            opacity: 1,
            backgroundColor: 'rgba(0, 0, 0, 0.2)'
          },
          width: 32,
          height: 32
        }}
        size="small"
        title={internalScrollLock ? "Unlock scrolling" : "Lock scrolling"}
      >
        {internalScrollLock ? <Lock fontSize="small" /> : <LockOpen fontSize="small" />}
      </IconButton>

      {/* Page Content */}
      <Box sx={{ mb: 4 }}>
        <ReaderContent 
          chapter={currentPageChapter}
          settings={settings}
        />
      </Box>

      {/* Page Navigation */}
      <Box sx={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        mt: 2,
        opacity: settings.showPages ? 1 : 0,
        transition: 'opacity 0.3s ease',
        gap: 2
      }}>
        <IconButton 
          onClick={(e) => {
            e.stopPropagation();
            goToPrevPage();
          }}
          disabled={currentPage === 0}
          sx={{ 
            visibility: currentPage === 0 ? 'hidden' : 'visible',
            color: settings.fontColor || 'inherit'
          }}
        >
          <KeyboardArrowLeft />
        </IconButton>

        {settings.showPages && pages.length > 1 && settings.showPageSlider && (
          <Box sx={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 2, 
            flex: 1,
            maxWidth: 300
          }}>
            <Slider
              value={currentPage + 1}
              min={1}
              max={pages.length}
              step={1}
              onChange={(_, value) => {
                goToPage((value as number) - 1);
              }}
              sx={{
                color: settings.fontColor || 'primary.main',
                '& .MuiSlider-thumb': {
                  backgroundColor: settings.fontColor || 'primary.main',
                },
                '& .MuiSlider-track': {
                  backgroundColor: settings.fontColor || 'primary.main',
                },
                '& .MuiSlider-rail': {
                  backgroundColor: settings.fontColor ? `${settings.fontColor}30` : 'rgba(0,0,0,0.2)',
                }
              }}
              size="small"
            />
            <Typography 
              variant="body2" 
              sx={{ 
                color: settings.fontColor || 'text.secondary',
                userSelect: 'none',
                minWidth: 'fit-content',
                whiteSpace: 'nowrap'
              }}
            >
              {currentPage + 1} / {pages.length}
            </Typography>
          </Box>
        )}

        {settings.showPages && (pages.length === 1 || !settings.showPageSlider) && (
          <Typography 
            variant="body2" 
            sx={{ 
              color: settings.fontColor || 'text.secondary',
              userSelect: 'none'
            }}
          >
            Page {currentPage + 1} of {pages.length}
          </Typography>
        )}

        <IconButton 
          onClick={(e) => {
            e.stopPropagation();
            goToNextPage();
          }}
          disabled={currentPage === pages.length - 1}
          sx={{ 
            visibility: currentPage === pages.length - 1 ? 'hidden' : 'visible',
            color: settings.fontColor || 'inherit'
          }}
        >
          <KeyboardArrowRight />
        </IconButton>
      </Box>
    </Box>
  );
};

export default PagedContent;
