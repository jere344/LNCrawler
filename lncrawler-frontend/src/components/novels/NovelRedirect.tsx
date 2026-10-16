import { use } from 'react';
import { Navigate, useLoaderData } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import RedirectWithNotification from '@components/common/RedirectWithNotification';
import type { AsyncData, NovelRedirectLoaderData } from '../../router/loaders';

const NovelRedirect = () => {
  const { t } = useTranslation();
  const { data: redirectPromise } = useLoaderData() as AsyncData<NovelRedirectLoaderData>;
  const result = use(redirectPromise);

  if (!result.ok) {
    return <RedirectWithNotification to="/" message={t('notifications.novelNotFound')} />;
  }

  return <Navigate to={result.target} replace />;
};

export default NovelRedirect;
