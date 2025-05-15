import React from 'react';
import {
  Grid,
  Paper,
  Typography,
  Divider,
  Zoom,
  Card,
  CardActionArea,
  CardContent,
  List,
  ListItem,
  ListItemText,
  Box,
  Chip,
  IconButton,
  Tooltip,
  alpha,
  useTheme,
} from '@mui/material';
import LanguageIcon from '@mui/icons-material/Language';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import BarChartIcon from '@mui/icons-material/BarChart';
import UpdateIcon from '@mui/icons-material/Update';
import PriorityHighIcon from '@mui/icons-material/PriorityHigh';
import ThumbUpIcon from '@mui/icons-material/ThumbUp';
import ThumbDownIcon from '@mui/icons-material/ThumbDown';
import TranslateIcon from '@mui/icons-material/Translate';
import { languageCodeToFlag, languageCodeToName } from '@utils/Misc';

interface NovelSourcesProps {
  novel: any;
  handleSourceClick: (sourceSlug: string) => void;
  handleVote: (sourceSlug: string, voteType: 'up' | 'down', event: React.MouseEvent) => void;
  votingInProgress: { [key: string]: boolean };
  formatDate: (dateString: string) => string;
}

const NovelSources: React.FC<NovelSourcesProps> = ({ novel, handleSourceClick, handleVote, votingInProgress, formatDate }) => {
  const theme = useTheme();

  return (
    <Paper
      elevation={3}
      sx={{
        p: 3,
        mb: 4,
        borderRadius: 3,
        background: theme.palette.mode === 'dark'
          ? `linear-gradient(135deg, ${alpha(theme.palette.background.paper, 0.9)} 0%, ${alpha(theme.palette.background.paper, 1)} 100%)`
          : theme.palette.background.paper,
      }}
    >
      <Typography
        variant="h5"
        gutterBottom
        sx={{
          display: 'flex',
          alignItems: 'center',
        }}
      >
        <LanguageIcon sx={{ mr: 1.5, color: theme.palette.primary.main }} />
        Available Sources
      </Typography>
      <Divider sx={{ mb: 3 }} />

      <Grid container spacing={3}>
        {novel.sources.map((source: any, index: number) => (
          <Grid item xs={12} sm={6} md={4} key={source.id}>
            <Zoom in={true} style={{ transitionDelay: `${index * 100}ms` }}>
              <Card
                sx={{
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  position: 'relative',
                  overflow: 'visible',
                }}
              >
                {index === 0 && (
                  <Box
                    sx={{
                      position: 'absolute',
                      top: -12,
                      right: 20,
                      zIndex: 2,
                      background: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.primary.dark} 100%)`,
                      color: 'white',
                      px: 2,
                      py: 0.5,
                      borderRadius: '4px',
                      boxShadow: '0 4px 10px rgba(0,0,0,0.15)',
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                    }}
                  >
                    <PriorityHighIcon fontSize="small" sx={{ mr: 0.5, fontSize: '1rem' }} />
                    PRIMARY
                  </Box>
                )}

                {/* Card content area (clickable) */}
                <Box sx={{ flexGrow: 1 }}>
                  <CardActionArea
                    onClick={() => handleSourceClick(source.source_slug)}
                    sx={{ height: '100%' }}
                  >
                    <CardContent>
                      <Typography
                        variant="h6"
                        gutterBottom
                        sx={{
                          display: 'flex',
                          alignItems: 'center',
                          color: theme.palette.primary.main,
                        }}
                      >
                        {source.source_name}
                      </Typography>

                      <List dense disablePadding>
                        {/* Add language info before chapters */}
                        <ListItem
                          disablePadding
                          sx={{
                            py: 0.5,
                            display: 'flex',
                            alignItems: 'center',
                          }}
                        >
                          <Box
                            sx={{
                              minWidth: 24,
                              height: 24,
                              borderRadius: '50%',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              mr: 1.5,
                              background: alpha(theme.palette.warning.main, 0.1),
                              color: theme.palette.warning.main,
                            }}
                          >
                            <TranslateIcon fontSize="small" />
                          </Box>
                          <ListItemText
                            primary={
                              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                                <Typography variant="body2" sx={{ fontWeight: 600, color: theme.palette.text.primary }}>
                                  Language
                                </Typography>
                                <Typography variant="body2" sx={{ fontWeight: 700, color: theme.palette.warning.main }}>
                                  {source.language ?
                                    (languageCodeToName(source.language || 'en') + ' ' + languageCodeToFlag(source.language || 'en') )
                                    : 'Unknown'}
                                </Typography>
                              </Box>
                            }
                          />
                        </ListItem>

                        <ListItem
                          disablePadding
                          sx={{
                            py: 0.5,
                            display: 'flex',
                            alignItems: 'center',
                          }}
                        >
                          <Box
                            sx={{
                              minWidth: 24,
                              height: 24,
                              borderRadius: '50%',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              mr: 1.5,
                              background: alpha(theme.palette.primary.main, 0.1),
                              color: theme.palette.primary.main,
                            }}
                          >
                            <MenuBookIcon fontSize="small" />
                          </Box>
                          <ListItemText
                            primary={
                              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                                <Typography variant="body2" sx={{ fontWeight: 600, color: theme.palette.text.primary }}>
                                  Chapters
                                </Typography>
                                <Typography variant="body2" sx={{ fontWeight: 700, color: theme.palette.primary.main }}>
                                  {source.chapters_count}
                                </Typography>
                              </Box>
                            }
                          />
                        </ListItem>

                        <ListItem
                          disablePadding
                          sx={{
                            py: 0.5,
                            display: 'flex',
                            alignItems: 'center',
                          }}
                        >
                          <Box
                            sx={{
                              minWidth: 24,
                              height: 24,
                              borderRadius: '50%',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              mr: 1.5,
                              background: alpha(theme.palette.secondary.main, 0.1),
                              color: theme.palette.secondary.main,
                            }}
                          >
                            <BarChartIcon fontSize="small" />
                          </Box>
                          <ListItemText
                            primary={
                              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                                <Typography variant="body2" sx={{ fontWeight: 600, color: theme.palette.text.primary }}>
                                  Status
                                </Typography>
                                <Chip
                                  label={source.status}
                                  size="small"
                                  sx={{
                                    height: 20,
                                    '& .MuiChip-label': { px: 1, py: 0, fontSize: '0.7rem' },
                                    bgcolor: source.status === 'Completed' ? theme.palette.success.main : theme.palette.info.main,
                                    color: '#fff',
                                  }}
                                />
                              </Box>
                            }
                          />
                        </ListItem>

                        <ListItem
                          disablePadding
                          sx={{
                            py: 0.5,
                            display: 'flex',
                            alignItems: 'center',
                          }}
                        >
                          <Box
                            sx={{
                              minWidth: 24,
                              height: 24,
                              borderRadius: '50%',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              mr: 1.5,
                              background: alpha(theme.palette.info.main, 0.1),
                              color: theme.palette.info.main,
                            }}
                          >
                            <UpdateIcon fontSize="small" />
                          </Box>
                          <ListItemText
                            primary={
                              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                                <Typography variant="body2" sx={{ fontWeight: 600, color: theme.palette.text.primary }}>
                                  Updated
                                </Typography>
                                <Typography variant="body2" sx={{ fontStyle: 'italic', fontSize: '0.7rem' }}>
                                  {formatDate(source.last_chapter_update)}
                                </Typography>
                              </Box>
                            }
                          />
                        </ListItem>
                      </List>
                    </CardContent>
                  </CardActionArea>
                </Box>

                {/* Voting area */}
                <Divider />
                <Box sx={{ p: 1, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Typography
                    variant="body2"
                    sx={{
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      color: theme.palette.text.secondary,
                    }}
                  >
                    Rating:
                    <Box
                      component="span"
                      sx={{
                        ml: 0.5,
                        color: source.vote_score > 0
                          ? theme.palette.success.main
                          : source.vote_score < 0
                            ? theme.palette.error.main
                            : 'inherit'
                      }}
                    >
                      {source.vote_score}
                    </Box>
                  </Typography>

                  <Box>
                    <Tooltip title="Upvote">
                      <IconButton
                        size="small"
                        color={source.user_vote === 'up' ? 'primary' : 'default'}
                        onClick={(e) => handleVote(source.source_slug, 'up', e)}
                        disabled={votingInProgress[source.source_slug]}
                        sx={{
                          color: source.user_vote === 'up' ? theme.palette.primary.main : alpha(theme.palette.text.primary, 0.6),
                          '&:hover': {
                            color: theme.palette.primary.main,
                            bgcolor: alpha(theme.palette.primary.main, 0.1),
                          }
                        }}
                      >
                        <ThumbUpIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>

                    <Tooltip title="Downvote">
                      <IconButton
                        size="small"
                        color={source.user_vote === 'down' ? 'error' : 'default'}
                        onClick={(e) => handleVote(source.source_slug, 'down', e)}
                        disabled={votingInProgress[source.source_slug]}
                        sx={{
                          color: source.user_vote === 'down' ? theme.palette.error.main : alpha(theme.palette.text.primary, 0.6),
                          '&:hover': {
                            color: theme.palette.error.main,
                            bgcolor: alpha(theme.palette.error.main, 0.1),
                          }
                        }}
                      >
                        <ThumbDownIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Box>
                </Box>
              </Card>
            </Zoom>
          </Grid>
        ))}
      </Grid>
    </Paper>
  );
};

export default NovelSources;
