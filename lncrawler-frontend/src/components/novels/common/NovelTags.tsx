import { Box, Chip, Typography, useTheme, alpha } from '@mui/material';
import BookmarkIcon from '@mui/icons-material/Bookmark'; // Optional: if you want an icon

interface NovelTagsProps {
  tags: string[];
  title?: string; // Optional title for the section
  titleVariant?: "h1" | "h2" | "h3" | "h4" | "h5" | "h6" | "subtitle1" | "subtitle2" | "body1" | "body2" | "caption" | "overline" | "inherit";
  chipSize?: "small" | "medium";
}

const NovelTags: React.FC<NovelTagsProps> = ({ 
  tags, 
  title = "Tags", 
  titleVariant = "h6", 
  chipSize = "medium" 
}) => {
  const theme = useTheme();

  if (!tags || tags.length === 0) {
    return null;
  }

  return (
    <Box>
      <Typography variant={titleVariant} gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
        <BookmarkIcon sx={{ mr: 1, color: theme.palette.secondary.main }} />
        {title}
      </Typography>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
        {tags.map((tag, index) => (
          <Chip 
            key={index} 
            label={tag} 
            size={chipSize} 
            variant="outlined" 
            sx={{
              borderColor: alpha(theme.palette.secondary.main, 0.5),
              color: theme.palette.text.primary, // Ensure text color is readable
              '&:hover': {
                bgcolor: alpha(theme.palette.secondary.main, 0.1),
              }
            }}
          />
        ))}
      </Box>
    </Box>
  );
};

export default NovelTags;
