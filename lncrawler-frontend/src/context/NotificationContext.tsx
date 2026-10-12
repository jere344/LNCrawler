import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Box, Collapse, type AlertColor } from '@mui/material';
import { useTranslation } from 'react-i18next';

export interface NotifyOptions {
    // Already-translated text shown in the toast.
    message: string;
    severity?: AlertColor;
    // Auto-dismiss delay in ms; null keeps the toast until it is closed.
    duration?: number | null;
    // Optional trailing element (e.g. an action button).
    action?: React.ReactNode;
}

interface NotificationItem {
    id: number;
    message: string;
    severity: AlertColor;
    duration: number | null;
    action?: React.ReactNode;
}

interface NotificationContextType {
    // Show a toast, returning its id so callers can dismiss it early.
    notify: (options: NotifyOptions) => number;
    dismiss: (id: number) => void;
}

const DEFAULT_DURATION = 5000;
// Beyond this, the oldest toast is dropped so a persistent/retriggering toast
// cannot grow the stack without bound.
const MAX_VISIBLE = 4;

const NotificationContext = createContext<NotificationContextType>({
    notify: () => 0,
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
                }}
            >
                {item.message}
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
            },
        ].slice(-MAX_VISIBLE));
        return id;
    }, []);

    const value = useMemo(() => ({ notify, dismiss }), [notify, dismiss]);

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
