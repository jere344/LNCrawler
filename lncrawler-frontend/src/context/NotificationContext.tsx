import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Box, Collapse, LinearProgress, type AlertColor } from '@mui/material';
import { useTranslation } from 'react-i18next';

export interface NotifyOptions {
    // Already-translated text shown in the toast.
    message: string;
    severity?: AlertColor;
    // Auto-dismiss delay in ms; null keeps the toast until it is closed.
    duration?: number | null;
    // Optional trailing element (e.g. an action button).
    action?: React.ReactNode;
    // Optional progress bar: 0-100 for determinate, 'indeterminate' for unknown.
    progress?: number | 'indeterminate';
}

interface NotificationItem {
    id: number;
    message: string;
    severity: AlertColor;
    duration: number | null;
    action?: React.ReactNode;
    progress?: number | 'indeterminate';
}

interface NotificationContextType {
    // Show a toast, returning its id so callers can dismiss it early.
    notify: (options: NotifyOptions) => number;
    // Changes an open toast in place; no-op if it was already dismissed.
    update: (id: number, options: Partial<NotifyOptions>) => void;
    dismiss: (id: number) => void;
}

const DEFAULT_DURATION = 5000;
// Beyond this, the oldest toast is dropped so a persistent/retriggering toast
// cannot grow the stack without bound.
const MAX_VISIBLE = 4;

const NotificationContext = createContext<NotificationContextType>({
    notify: () => 0,
    update: () => {},
    dismiss: () => {},
});

export const useNotification = () => useContext(NotificationContext);

// One toast owns its auto-dismiss timer, so removing it never affects the rest.
const NotificationToast: React.FC<{ item: NotificationItem; onDismiss: (id: number) => void }> = ({ item, onDismiss }) => {
    const { t } = useTranslation();
    const [open, setOpen] = useState(true);

    useEffect(() => {
        if (item.duration === null) return;
        const timer = window.setTimeout(() => setOpen(false), item.duration);
        return () => window.clearTimeout(timer);
    }, [item.duration]);

    return (
        <Collapse in={open} onExited={() => onDismiss(item.id)} unmountOnExit>
            <Alert
                severity={item.severity}
                variant="filled"
                onClose={() => setOpen(false)}
                action={item.action}
                slotProps={{
                    closeButton: { 'aria-label': t('notifications.dismiss') },
                    // Errors/warnings interrupt; success/info announce politely.
                    root: { role: item.severity === 'error' || item.severity === 'warning' ? 'alert' : 'status' },
                }}
                sx={{
                    width: { xs: 'calc(100vw - 32px)', sm: 360 },
                    boxShadow: 3,
                    ...(item.progress !== undefined && { '& .MuiAlert-message': { flexGrow: 1 } }),
                }}
            >
                {item.progress === undefined ? (
                    item.message
                ) : (
                    <Box sx={{ width: '100%' }}>
                        {item.message}
                        {typeof item.progress === 'number' ? (
                            <LinearProgress variant="determinate" value={item.progress} color="inherit" sx={{ mt: 1 }} />
                        ) : (
                            <LinearProgress variant="indeterminate" color="inherit" sx={{ mt: 1 }} />
                        )}
                    </Box>
                )}
            </Alert>
        </Collapse>
    );
};

export const NotificationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [items, setItems] = useState<NotificationItem[]>([]);
    const nextId = useRef(0);

    const dismiss = useCallback((id: number) => {
        setItems((prev) => prev.filter((item) => item.id !== id));
    }, []);

    const notify = useCallback((options: NotifyOptions) => {
        const id = nextId.current++;
        setItems((prev) => [
            ...prev,
            {
                id,
                message: options.message,
                severity: options.severity ?? 'error',
                duration: options.duration === undefined ? DEFAULT_DURATION : options.duration,
                action: options.action,
                progress: options.progress,
            },
        ].slice(-MAX_VISIBLE));
        return id;
    }, []);

    const update = useCallback((id: number, options: Partial<NotifyOptions>) => {
        setItems((prev) => prev.map((item) => {
            if (item.id !== id) return item;
            const next = { ...item };
            // Only keys present in `options` change, so `progress: undefined` removes the bar.
            if ('message' in options && options.message !== undefined) next.message = options.message;
            if ('severity' in options) next.severity = options.severity ?? 'error';
            if ('duration' in options) next.duration = options.duration === undefined ? DEFAULT_DURATION : options.duration;
            if ('action' in options) next.action = options.action;
            if ('progress' in options) next.progress = options.progress;
            return next;
        }));
    }, []);

    const value = useMemo(() => ({ notify, update, dismiss }), [notify, update, dismiss]);

    return (
        <NotificationContext.Provider value={value}>
            {children}
            {/* Fixed, stacked top-right; logical inset flips it under RTL. */}
            <Box
                sx={{
                    position: 'fixed',
                    top: 16,
                    insetInlineEnd: 16,
                    zIndex: (theme) => theme.zIndex.snackbar,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-end',
                    gap: 1,
                    pointerEvents: 'none',
                    '& > *': { pointerEvents: 'auto' },
                }}
            >
                {items.map((item) => (
                    <NotificationToast key={item.id} item={item} onDismiss={dismiss} />
                ))}
            </Box>
        </NotificationContext.Provider>
    );
};
