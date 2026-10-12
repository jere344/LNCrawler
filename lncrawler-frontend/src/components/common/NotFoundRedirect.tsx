import { useTranslation } from 'react-i18next';
import RedirectWithNotification from './RedirectWithNotification';

/** Catch-all route: translate the "page not found" message in a component. */
const NotFoundRedirect = () => {
  const { t } = useTranslation();
  return (
    <RedirectWithNotification
      to="/"
      message={t('notifications.pageNotFound')}
      severity="warning"
    />
  );
};

export default NotFoundRedirect;
