import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useNotification, type NotifyOptions } from '@context/NotificationContext';

interface Props {
    to: string;
    message: string;
    severity?: NotifyOptions['severity'];
}

/**
 * Shows a notification explaining why the user is being redirected, then
 * navigates. The NotificationProvider sits above the routes, so the toast
 * outlives this component's unmount.
 */
const RedirectWithNotification: React.FC<Props> = ({ to, message, severity = 'error' }) => {
    const { notify } = useNotification();
    const navigate = useNavigate();
    const fired = useRef(false);

    useEffect(() => {
        // Guard against StrictMode's double-invoked effects in development.
        if (fired.current) return;
        fired.current = true;
        notify({ message, severity });
        navigate(to, { replace: true });
    }, [notify, navigate, to, message, severity]);

    return null;
};

export default RedirectWithNotification;
