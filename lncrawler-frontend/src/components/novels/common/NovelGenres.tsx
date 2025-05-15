import { Box, Chip, Typography, useTheme, alpha } from '@mui/material';
import BookmarkIcon from '@mui/icons-material/Bookmark'; // Optional: if you want an icon

interface NovelGenresProps {
  genres: string[];
  title?: string; // Optional title for the section
  titleVariant?: "h1" | "h2" | "h3" | "h4" | "h5" | "h6" | "subtitle1" | "subtitle2" | "body1" | "body2" | "caption" | "overline" | "inherit";
  chipSize?: "small" | "medium";
  textColor?: string;
  showTitle?: boolean;
}

const NovelGenres: React.FC<NovelGenresProps> = ({ 
  genres, 
  title = "Genres", 
  titleVariant = "subtitle2", 
  chipSize = "small",
  textColor,
  showTitle = true,
}) => {
  const theme = useTheme();

  if (!genres || genres.length === 0) {
    return null;
  }

  return (
    <Box sx={{ mb: 2 }}>
      {showTitle && (
        <Typography 
          variant={titleVariant}
          sx={{ 
            color: textColor || alpha(theme.palette.common.white, 0.7), // Default to white for hero, adaptable otherwise
            mb: 1,
            display: 'flex',
            alignItems: 'center',
          }}
        >
          {/* Optional: <BookmarkIcon sx={{ mr: 1, fontSize: '1rem', color: textColor || theme.palette.primary.main }} /> */}
          {title}:
        </Typography>
      )}
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
        {genres.map((genre, index) => {
          const hue = (index * 40) % 360;
          const color = `hsla(${hue}, 70%, 60%, 0.7)`;
          
          return (
            <Chip 
              key={index} 
              label={genre} 
              size={chipSize}
              sx={{ 
                bgcolor: color,
                color: theme.palette.common.white,
                fontWeight: 500,
                backdropFilter: 'blur(10px)',
                '&:hover': {
                  bgcolor: `hsla(${hue}, 70%, 50%, 0.8)`,
                }
              }} 
            />
          );
        })}
      </Box>
    </Box>
  );
};

export default NovelGenres;
