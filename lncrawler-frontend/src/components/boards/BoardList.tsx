import { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  CircularProgress,
  Alert,
  Container,
  Paper,
  Divider,
  Avatar,
  useTheme,
  alpha
} from '@mui/material';
import { Link } from 'react-router-dom';
import ChatIcon from '@mui/icons-material/Chat';
import ForumIcon from '@mui/icons-material/Forum';
import CommentIcon from '@mui/icons-material/Comment';
import { boardService } from '../../services/board.service';

interface Board {
  id: string;
  name: string;
  slug: string;
  description: string;
  created_at: string;
  comment_count: number;
  is_active: boolean;
}

// Array of colors for the icons
const iconColors = [
  '#3f51b5', // indigo
  '#f44336', // red
  '#4caf50', // green
  '#ff9800', // orange
  '#9c27b0', // purple
  '#2196f3', // blue
  '#009688', // teal
  '#795548', // brown
];

// Function to generate a consistent color from a board name
const getBoardColor = (boardName: string) => {
  // Simple hash function to convert string to number
  let hash = 0;
  for (let i = 0; i < boardName.length; i++) {
    hash = boardName.charCodeAt(i) + ((hash << 5) - hash);
  }
  
  // Get a consistent color from our color palette
  const colorIndex = Math.abs(hash) % iconColors.length;
  return iconColors[colorIndex];
};

const BoardList = () => {
  const theme = useTheme();
  const [boards, setBoards] = useState<Board[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchBoards = async () => {
      try {
        const fetchedBoards = await boardService.listBoards();
        setBoards(fetchedBoards);
      } catch (err) {
        console.error('Failed to fetch boards:', err);
        setError('Failed to load boards. Please try refreshing the page.');
      } finally {
        setLoading(false);
      }
    };

    fetchBoards();
  }, []);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ my: 2 }}>
        {error}
      </Alert>
    );
  }

  return (
    <Container maxWidth="lg">
      <Paper 
        elevation={0} 
        sx={{ 
          py: 4, 
          px: 3, 
          mb: 4, 
          borderRadius: 2,
          background: `linear-gradient(to right, ${alpha(theme.palette.primary.main, 0.1)}, ${theme.palette.background.paper})`,
          border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
        }}
      >
        <Typography variant="h4" gutterBottom sx={{ mb: 2, fontWeight: 600, display: 'flex', alignItems: 'center' }}>
          <ForumIcon sx={{ mr: 1, fontSize: 32 }} /> Chat Boards
        </Typography>
        
        <Typography variant="body1" color="text.secondary" sx={{ mb: 2, maxWidth: '800px' }}>
          Join discussions in our community boards. Share your thoughts, ask questions, and connect with other readers.
        </Typography>
      </Paper>

      <Grid container spacing={3}>
        {boards.map((board) => {
          const boardColor = getBoardColor(board.name);
          return (
            <Grid item xs={12} sm={6} md={4} key={board.id}>
              <Card 
                component={Link}
                to={`/boards/${board.slug}`}
                sx={{ 
                  textDecoration: 'none',
                  height: '100%',
                  transition: 'all 0.3s',
                  borderRadius: 2,
                  display: 'flex',
                  flexDirection: 'column',
                  border: `1px solid ${theme.palette.divider}`,
                  overflow: 'visible',
                  position: 'relative',
                  '&:hover': {
                    transform: 'translateY(-3px)',
                    boxShadow: theme.shadows[3],
                    border: `1px solid ${alpha(boardColor, 0.4)}`,
                  }
                }}
              >
                <Box 
                  sx={{
                    position: 'absolute',
                    top: -15,
                    left: 20,
                    backgroundColor: theme.palette.background.paper,
                    borderRadius: '50%',
                    width: 44,
                    height: 44,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    border: `1px solid ${alpha(boardColor, 0.3)}`,
                    boxShadow: theme.shadows[1],
                    zIndex: 1,
                  }}
                >
                  <Avatar sx={{ bgcolor: alpha(boardColor, 0.15) }}>
                    <CommentIcon sx={{ color: boardColor, fontSize: 24 }} />
                  </Avatar>
                </Box>
                
                <CardContent sx={{ pt: 3, pb: 2, flexGrow: 1 }}>
                  <Box sx={{ mb: 1, mt: 1, display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="h6" component="h2" sx={{ fontWeight: 500 }}>
                      {board.name}
                    </Typography>
                  </Box>
                  
                  <Typography 
                    variant="body2" 
                    color="text.secondary" 
                    sx={{ mb: 2, minHeight: '2.5em', lineHeight: 1.4 }}
                  >
                    {board.description || 'No description available'}
                  </Typography>
                </CardContent>
                
                <Divider />
                
                <Box sx={{ px: 2, py: 1.5, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    <ChatIcon 
                      fontSize="small" 
                      sx={{ 
                        mr: 0.5, 
                        fontSize: '0.9rem', 
                        color: boardColor
                      }} 
                    />
                    <Typography 
                      variant="body2" 
                      fontWeight={500} 
                      sx={{ color: boardColor }}
                    >
                      {board.comment_count}
                    </Typography>
                  </Box>
                  <Typography variant="caption" color="text.secondary">
                    {new Date(board.created_at).toLocaleDateString(undefined, { 
                      month: 'short', 
                      day: 'numeric', 
                      year: 'numeric' 
                    })}
                  </Typography>
                </Box>
              </Card>
            </Grid>
          );
        })}
      </Grid>

      {boards.length === 0 && (
        <Paper 
          sx={{ 
            textAlign: 'center', 
            py: 6, 
            px: 3,
            borderRadius: 2, 
            backgroundColor: alpha(theme.palette.primary.main, 0.03),
            border: `1px dashed ${alpha(theme.palette.primary.main, 0.2)}`,
          }}
        >
          <ForumIcon sx={{ fontSize: 60, color: alpha(theme.palette.text.secondary, 0.5), mb: 2 }} />
          <Typography variant="h6" color="text.secondary" gutterBottom>
            No boards available
          </Typography>
          <Typography variant="body2" color="text.secondary">
            There are currently no discussion boards. Please check back later.
          </Typography>
        </Paper>
      )}
    </Container>
  );
};

export default BoardList;
