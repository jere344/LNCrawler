import { Box, Grid, Pagination } from '@mui/material';
import { useTranslation } from 'react-i18next';
import PlaylistAddIcon from '@mui/icons-material/PlaylistAdd';
import SectionContainer from '@components/common/SectionContainer.tsx';
import ReadingListCard from '../../readinglist/ReadingListCard';
import { NovelDetail } from '@models/novels_types';

const READING_LISTS_PER_PAGE = 5;

const ReadingListsPanel = ({
  readingLists,
  page,
  onPageChange,
}: {
  readingLists: NonNullable<NovelDetail['reading_lists']>;
  page: number;
  onPageChange: (page: number) => void;
}) => {
  const { t } = useTranslation();
  const readingListsPageCount = Math.ceil(readingLists.length / READING_LISTS_PER_PAGE);
  const currentReadingListPage = Math.min(page, readingListsPageCount);
  const visibleReadingLists = readingLists.slice(
    (currentReadingListPage - 1) * READING_LISTS_PER_PAGE,
    currentReadingListPage * READING_LISTS_PER_PAGE
  );
  return (
    <SectionContainer title={t('sourceDetail.inReadingLists')} icon={<PlaylistAddIcon />}>
      <Grid container spacing={2}>
        {visibleReadingLists.map((list) => (
          <Grid size={{ xs: 12, sm: 6, md: 4 }} key={list.id}>
            <ReadingListCard list={list} />
          </Grid>
        ))}
      </Grid>
      {readingListsPageCount > 1 && (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
          <Pagination
            count={readingListsPageCount}
            page={currentReadingListPage}
            onChange={(_, page) => onPageChange(page)}
            color="primary"
          />
        </Box>
      )}
    </SectionContainer>
  );
};

export default ReadingListsPanel;
