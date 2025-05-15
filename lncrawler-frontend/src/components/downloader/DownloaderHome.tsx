import { Container, Typography, Box, Paper } from '@mui/material';
import SearchForm from './SearchForm';
import DownloadStepper from './DownloadStepper';

const DownloaderHome = () => {
    return (
        <Container maxWidth="md">
            <Box sx={{ my: 4, textAlign: 'center' }}>
                <Typography variant="h1" component="h1" gutterBottom>
                    Add a novel
                </Typography>
                <Typography variant="subtitle1" color="text.primary" component="h2" gutterBottom>
                    Automatically and easily add your favorite novels to our library.
                </Typography>
                <Typography variant="body1" color="text.primary" component="p" gutterBottom>
                    Use the search form below and we will search through our 300+ supported sources to find the novel you want, and add it to our library for anyone to read.
                    You can also enter the URL to the novel from any of our supported sources to skip the search process.
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
