import React from 'react';
import { useTranslation } from 'react-i18next';
import ConfirmDialog from '@components/common/ConfirmDialog';
import { getNovelDisplayTitle } from '@utils/Misc';
import { Novel } from '@models/novels_types';

interface MarkAsReadConfirmDialogProps {
  open: boolean;
  novel: Novel;
  loading?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

// Asks before marking the novel's latest chapter as read.
const MarkAsReadConfirmDialog: React.FC<MarkAsReadConfirmDialogProps> = ({ open, novel, loading, onConfirm, onClose }) => {
  const { t } = useTranslation();

  return (
    <ConfirmDialog
      open={open}
      title={t('markAsRead.confirmTitle')}
      message={t('markAsRead.confirmBody', { title: getNovelDisplayTitle(novel) })}
      confirmLabel={t('markAsRead.confirm')}
      loading={loading}
      onConfirm={onConfirm}
      onClose={onClose}
    />
  );
};

export default MarkAsReadConfirmDialog;
