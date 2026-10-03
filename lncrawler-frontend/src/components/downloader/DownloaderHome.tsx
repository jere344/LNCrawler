import { Container, Typography, Box, Paper } from '@mui/material';
import { useTranslation } from 'react-i18next';
import SearchForm from './SearchForm';
import DownloadStepper from './DownloadStepper';

const DownloaderHome = () => {
    const { t } = useTranslation();

    return (
        <Container maxWidth="md">
            <Box sx={{ my: 4, textAlign: 'center' }}>
                <Typography variant="h1" component="h1" gutterBottom>
                    {t('downloader.addNovelHeading')}
                </Typography>
                <Typography variant="subtitle1" component="h2" gutterBottom sx={{
                    color: "text.primary"
                }}>
                    {t('downloader.addNovelSubtitle')}
                </Typography>
                <Typography variant="body1" component="p" gutterBottom sx={{
                    color: "text.primary"
                }}>
                    {t('downloader.addNovelBody')}
                </Typography>
            </Box>

            <DownloadStepper activeStep="search" />

            <Paper elevation={3} sx={{ p: 3, mb: 4 }}>
                <SearchForm />
            </Paper>
        </Container>
    );
};

export default DownloaderHome;
