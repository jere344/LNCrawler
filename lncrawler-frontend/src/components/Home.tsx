import { Container, Typography, Box, Paper } from '@mui/material';
import SearchForm from './SearchForm';

const Home = () => {
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
        </Container>
    );
};

export default Home;
