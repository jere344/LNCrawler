import { Box, Container, Typography, Link, Divider, Grid, useMediaQuery, Button } from "@mui/material";
import { useTheme as useMuiTheme } from '@mui/material/styles';
import GitHubIcon from '@mui/icons-material/GitHub';
import LinkedInIcon from '@mui/icons-material/LinkedIn';
import EmailIcon from '@mui/icons-material/Email';

// Footer component with developer information and links
const Footer = () => {
    const muiTheme = useMuiTheme();
    const isMobile = useMediaQuery(muiTheme.breakpoints.down('sm'));
    const currentYear = new Date().getFullYear();

    return (
        <Box
            component="footer"
            sx={{
                py: 4,
                px: 2,
                mt: 'auto',
                backgroundColor: muiTheme.palette.mode === 'dark' 
                    ? 'rgba(0, 0, 0, 0.05)' 
                    : 'rgba(0, 0, 0, 0.02)',
                borderTop: `1px solid ${muiTheme.palette.divider}`,
            }}
        >
            <Container maxWidth="lg">
                <Grid container spacing={4} justifyContent="space-between">
                    <Grid item xs={12} sm={6} md={4}>
                        <Typography variant="h6" color="text.primary" gutterBottom fontWeight="bold">
                            LNCrawler
                        </Typography>
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                            Read Asian Light Novels from 300+ Sources
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            MIT License © {currentYear} LNCrawler.
                        </Typography>
                    </Grid>

                    <Grid item xs={12} sm={6} md={4}>
                        <Typography variant="subtitle1" color="text.primary" gutterBottom fontWeight="bold">
                            Links
                        </Typography>
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                            <Link href="https://discord.gg/a2b4Mfr4cU" target="_blank" rel="noopener noreferrer" 
                                sx={{ 
                                    display: 'inline-flex', 
                                    alignItems: 'center',
                                    color: 'text.secondary',
                                    '&:hover': { color: 'primary.main' },
                                }}>
                                Discord Community
                            </Link>
                            <Link href="https://github.com/jere344/lightnovel-crawler-website" target="_blank" rel="noopener noreferrer" 
                                sx={{ 
                                    display: 'inline-flex', 
                                    alignItems: 'center',
                                    color: 'text.secondary',
                                    '&:hover': { color: 'primary.main' },
                                }}>
                                GitHub Repository
                            </Link>
                            <Link href="mailto:jeremy.guerin34@yahoo.com?subject=DMCA%20Notice" 
                                sx={{ 
                                    display: 'inline-flex', 
                                    alignItems: 'center',
                                    color: 'text.secondary',
                                    '&:hover': { color: 'primary.main' },
                                }}>
                                <EmailIcon fontSize="small" sx={{ mr: 0.5 }} />
                                DMCA Contact
                            </Link>
                        </Box>
                    </Grid>

                    <Grid item xs={12} sm={6} md={4}>
                        <Typography variant="subtitle1" color="text.primary" gutterBottom fontWeight="bold">
                            Developed by jere344
                        </Typography>
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                            <Link href="https://github.com/jere344" target="_blank" rel="noopener noreferrer" 
                                sx={{ 
                                    display: 'inline-flex', 
                                    alignItems: 'center',
                                    color: 'text.secondary',
                                    '&:hover': { color: 'primary.main' },
                                }}>
                                <GitHubIcon fontSize="small" sx={{ mr: 1 }} />
                                GitHub
                            </Link>
                            <Link href="https://www.linkedin.com/in/jérémy-guerin-b9019b255/" target="_blank" rel="noopener noreferrer" 
                                sx={{ 
                                    display: 'inline-flex', 
                                    alignItems: 'center',
                                    color: 'text.secondary',
                                    '&:hover': { color: 'primary.main' },
                                }}>
                                <LinkedInIcon fontSize="small" sx={{ mr: 1 }} />
                                LinkedIn
                            </Link>
                        </Box>
                    </Grid>
                </Grid>

                <Divider sx={{ mt: 4, mb: 3 }} />

                <Box sx={{ display: 'flex', justifyContent: 'center', flexWrap: 'wrap', textAlign: 'center' }}>
                    <Typography variant="caption" color="text.secondary">
                        LNCrawler is not affiliated with any of the sources. All content belongs to their respective owners.
                        We are not responsible for the content of external sites and will do our best to remove infringing content upon request.
                    </Typography>
                </Box>
            </Container>
        </Box>
    );
};

export default Footer;
