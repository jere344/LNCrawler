import { useLoaderData } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import RedirectWithNotification from '@components/common/RedirectWithNotification';
import type { NovelRedirectLoaderData } from '../../router/loaders';

const NovelRedirect = () => {
  const { t } = useTranslation();
  const data = useLoaderData() as NovelRedirectLoaderData;

  if (!data.ok) {
    return <RedirectWithNotification to="/" message={t('notifications.novelNotFound')} />;
  }

  // A successful load threw a redirect in the loader; nothing to render.
  return null;
};

export default NovelRedirect;
