import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { useAuth } from '@context/AuthContext';
import type { ShowR18 } from '../models/user_types';

interface AdultContentContextType {
    // Account preference; anonymous visitors are treated as 'no'.
    showR18: ShowR18;
    // True when covers of adult novels must be blurred ('blur' preference).
    blurCovers: boolean;
    isRevealed: (id?: string) => boolean;
    reveal: (id?: string) => void;
    isBlurred: (isAdult?: boolean, id?: string) => boolean;
    // Attach to a blurred cover/badge so clicking it reveals that cover.
    revealHandler: (id?: string) => (event: React.MouseEvent) => void;
}

const noop = () => {};
const AdultContentContext = createContext<AdultContentContextType>({
    showR18: 'no',
    blurCovers: false,
    isRevealed: () => false,
    reveal: noop,
    isBlurred: () => false,
    revealHandler: () => noop,
});

export const useAdultContent = () => useContext(AdultContentContext);

export const AdultContentProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const { user } = useAuth();
    const showR18: ShowR18 = user?.show_r18 ?? 'no';
    const blurCovers = showR18 === 'blur';

    // Covers the user chose to reveal this session, keyed by novel id.
    const [revealed, setRevealed] = useState<Set<string>>(new Set());

    const isRevealed = useCallback((id?: string) => !!id && revealed.has(id), [revealed]);
    const reveal = useCallback((id?: string) => {
        if (!id) return;
        setRevealed((prev) => (prev.has(id) ? prev : new Set(prev).add(id)));
    }, []);

    const isBlurred = useCallback(
        (isAdult?: boolean, id?: string) => blurCovers && !!isAdult && !isRevealed(id),
        [blurCovers, isRevealed],
    );

    const revealHandler = useCallback(
        (id?: string) => (event: React.MouseEvent) => {
            if (!isRevealed(id)) {
                event.stopPropagation();
                event.preventDefault();
                reveal(id);
            }
        },
        [isRevealed, reveal],
    );

    const value = useMemo(
        () => ({ showR18, blurCovers, isRevealed, reveal, isBlurred, revealHandler }),
        [showR18, blurCovers, isRevealed, reveal, isBlurred, revealHandler],
    );

    return <AdultContentContext.Provider value={value}>{children}</AdultContentContext.Provider>;
};
