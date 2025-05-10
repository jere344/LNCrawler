import { Container, Typography, Box, Paper, Button } from '@mui/material';
import { Link } from 'react-router-dom';
import SearchForm from './SearchForm';
import LibraryBooksIcon from '@mui/icons-material/LibraryBooks';

const DownloaderHome = () => {
    return (
        <Container maxWidth="md">
            <Box sx={{ my: 4, textAlign: 'center' }}>
                <Typography variant="h4" component="h1" gutterBottom>
                    Novel Reader & Downloader
                </Typography>
                <Typography variant="subtitle1" color="text.secondary" paragraph>
                    Search and download your favorite light novels
                </Typography>
            </Box>
            
            <Paper elevation={3} sx={{ p: 3, mb: 4 }}>
                <SearchForm />
            </Paper>
            
            <Box sx={{ textAlign: 'center', my: 3 }}>
                <Button 
                    component={Link} 
                    to="/novels" 
                    variant="outlined" 
                    color="primary" 
                    startIcon={<LibraryBooksIcon />}
                    size="large"
                >
                    Browse Novel Library
                </Button>
            </Box>
        </Container>
    );
};

export default DownloaderHome;
