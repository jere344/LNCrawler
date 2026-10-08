import { Container, Typography, Box, Paper, Button } from '@mui/material';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import SearchForm from './SearchForm';
import DownloadStepper from './DownloadStepper';

const DownloaderHome = () => {
    const { t } = useTranslation();

    return (
        <Container maxWidth="md">
            <Box sx={{ my: 1, textAlign: 'center' }}>
                <Typography variant="h5" component="h1" gutterBottom>
                    {t('downloader.addNovelHeading')}
                </Typography>
                <Typography variant="body2" component="h2" gutterBottom sx={{
                    color: "text.primary"
                }}>
                    {t('downloader.addNovelSubtitle')}
                </Typography>
                <Typography variant="body2" component="p" gutterBottom sx={{
                    color: "text.primary"
                }}>
                    {t('downloader.addNovelBody')}
                </Typography>
            </Box>

            <DownloadStepper activeStep="search" />

            <Paper elevation={3} sx={{ p: 1.5 }}>
                <SearchForm />
            </Paper>

            <Box sx={{ mt: 2, textAlign: 'center' }}>
                <Button variant="outlined" component={Link} to="/download/jobs">
                    {t('downloader.jobsLink')}
                </Button>
            </Box>
        </Container>
    );
};

export default DownloaderHome;
