import { Box, Chip, useTheme, alpha, Button } from '@mui/material';
import { useState } from 'react';
import { Link } from 'react-router-dom';

interface NovelTagsProps {
  tags: string[];
  chipSize?: "small" | "medium";
  maxVisible?: number;
}

const NovelTags: React.FC<NovelTagsProps> = ({ 
  tags, 
  chipSize = "medium",
  maxVisible = 20
}) => {
  const theme = useTheme();
  const [showAll, setShowAll] = useState(false);

  if (!tags || tags.length === 0) {
    return null;
  }

  const displayTags = showAll ? tags : tags.slice(0, maxVisible);
  const hasMore = tags.length > maxVisible;

  return (
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
        {displayTags.map((tag, index) => (
          <Link
            to={`/novels/search?tag=${encodeURIComponent(tag)}`}
            key={index}
            style={{ textDecoration: 'none' }}
          >
            <Chip
              label={tag}
              size={chipSize}
              variant="outlined" 
              clickable
              sx={{
                borderColor: alpha(theme.palette.secondary.main, 0.5),
                color: theme.palette.text.primary,
                '&:hover': {
                  bgcolor: alpha(theme.palette.secondary.main, 0.1),
                }
              }}
            />
          </Link>
        ))}
        {hasMore && (
          <Button 
            size="small" 
            onClick={() => setShowAll(!showAll)} 
            sx={{ 
              color: theme.palette.secondary.main,
              minWidth: 'auto',
              py: 0.5
            }}
          >
            {showAll ? 'Show Less' : `+${tags.length - maxVisible} More`}
          </Button>
        )}
      </Box>
  );
};

export default NovelTags;
