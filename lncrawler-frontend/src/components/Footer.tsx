import { Box, Container, Typography, Link, Divider, Grid } from "@mui/material";
import { useTheme as useMuiTheme } from '@mui/material/styles';
import { useTranslation } from "react-i18next";
import GitHubIcon from '@mui/icons-material/GitHub';
import LinkedInIcon from '@mui/icons-material/LinkedIn';
import EmailIcon from '@mui/icons-material/Email';

// Footer component with developer information and links
const Footer = () => {
    const muiTheme = useMuiTheme();
    const { t } = useTranslation();
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
                <Grid container spacing={4} sx={{
                    justifyContent: "space-between"
                }}>
                    <Grid
                        size={{
                            xs: 12,
                            sm: 6,
                            md: 4
                        }}>
                        <Typography
                            variant="h6"
                            gutterBottom
                            sx={{
                                color: "text.primary",
                                fontWeight: "bold"
                            }}>
                            LNCrawler
                        </Typography>
                        <Typography
                            variant="body2"
                            sx={{
                                color: "text.secondary",
                                mb: 2
                            }}>
                            {t('footer.tagline')}
                        </Typography>
                        <Typography variant="body2" sx={{
                            color: "text.secondary"
                        }}>
                            {t('footer.copyright', { year: currentYear })}
                        </Typography>
                    </Grid>

                    <Grid
                        size={{
                            xs: 12,
                            sm: 6,
                            md: 4
                        }}>
                        <Typography
                            variant="subtitle1"
                            gutterBottom
                            sx={{
                                color: "text.primary",
                                fontWeight: "bold"
                            }}>
                            {t('footer.links')}
                        </Typography>
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                            <Link href="https://github.com/jere344/LNCrawler" target="_blank" rel="noopener noreferrer" 
                                sx={{ 
                                    display: 'inline-flex', 
                                    alignItems: 'center',
                                    color: 'text.secondary',
                                    '&:hover': { color: 'primary.main' },
                                }}>
                                {t('footer.githubRepository')}
                            </Link>
                            <Link href="mailto:jeremy.guerin34@yahoo.com?subject=DMCA%20Notice" 
                                sx={{ 
                                    display: 'inline-flex', 
                                    alignItems: 'center',
                                    color: 'text.secondary',
                                    '&:hover': { color: 'primary.main' },
                                }}>
                                <EmailIcon fontSize="small" sx={{ mr: 0.5 }} />
                                {t('footer.dmcaContact')}
                            </Link>
                        </Box>
                    </Grid>

                    <Grid
                        size={{
                            xs: 12,
                            sm: 6,
                            md: 4
                        }}>
                        <Typography
                            variant="subtitle1"
                            gutterBottom
                            sx={{
                                color: "text.primary",
                                fontWeight: "bold"
                            }}>
                            {t('footer.developedBy')}
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
                                {t('footer.github')}
                            </Link>
                            <Link href="https://www.linkedin.com/in/jérémy-guerin-b9019b255/" target="_blank" rel="noopener noreferrer" 
                                sx={{ 
                                    display: 'inline-flex', 
                                    alignItems: 'center',
                                    color: 'text.secondary',
                                    '&:hover': { color: 'primary.main' },
                                }}>
                                <LinkedInIcon fontSize="small" sx={{ mr: 1 }} />
                                {t('footer.linkedin')}
                            </Link>
                        </Box>
                    </Grid>
                </Grid>

                <Divider sx={{ mt: 4, mb: 3 }} />

                <Box sx={{ display: 'flex', justifyContent: 'center', flexWrap: 'wrap', textAlign: 'center' }}>
                    <Typography variant="caption" sx={{
                        color: "text.secondary"
                    }}>
                        {t('footer.disclaimer')}
                    </Typography>
                </Box>
            </Container>
        </Box>
    );
};

export default Footer;
