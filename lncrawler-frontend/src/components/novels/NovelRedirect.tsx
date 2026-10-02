import { useEffect, useState } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { Box, CircularProgress } from '@mui/material';
import { novelService } from '../../services/api';
import { getNovelSourcePath } from '@utils/Misc';

const NovelRedirect = () => {
  const { novelSlug } = useParams<{ novelSlug: string }>();
  const [target, setTarget] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const resolve = async () => {
      if (!novelSlug) return;
      try {
        const novel = await novelService.getNovelDetail(novelSlug);
        setTarget(getNovelSourcePath(novel) || null);
      } catch {
        setFailed(true);
      }
    };
    resolve();
  }, [novelSlug]);

  if (failed) return <Navigate to="/" replace />;
  if (target) return <Navigate to={target} replace />;

  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', my: 8 }}>
      <CircularProgress />
    </Box>
  );
};

export default NovelRedirect;
