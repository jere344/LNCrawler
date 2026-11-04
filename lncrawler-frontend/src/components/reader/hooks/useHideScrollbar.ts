import { useEffect } from 'react';

// Hides the page scrollbar while the reader setting asks for it
export function useHideScrollbar(hideScrollbar: boolean) {
  useEffect(() => {
    if (!hideScrollbar) return;
    // Add a style to hide scrollbar
    const styleElement = document.createElement('style');
    styleElement.id = 'hide-scrollbar-style';
    styleElement.textContent = `
      html { scrollbar-width: none; }
      body { -ms-overflow-style: none; }
      body::-webkit-scrollbar, body::-webkit-scrollbar-button { display: none; }
    `;
    document.head.appendChild(styleElement);

    // Removes the style when the setting turns off or the component unmounts
    return () => {
      document.getElementById('hide-scrollbar-style')?.remove();
    };
  }, [hideScrollbar]);
}
