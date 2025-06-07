import { Card, Typography, Box, Chip, Avatar, CardMedia } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import { ReadingList } from "@models/readinglist_types";
import BookIcon from "@mui/icons-material/Book";
import { formatTimeAgo } from "@utils/Misc";

interface ReadingListCardProps {
    list: ReadingList;
}

const ReadingListCard = ({ list }: ReadingListCardProps) => {
    const firstItemCover = list.first_item?.novel.prefered_source?.cover_min_url;
    const defaultCoverBg = "linear-gradient(135deg, #0a3d91 0%, #1e88e5 100%)";
    const coverHeight = 160;
    const coverWidth = 120;

    return (
        <Box
            sx={{
                display: "flex",
                justifyContent: "flex-start",
                height: coverHeight + "px",
                width: "100%",
                transition: "transform 0.2s",
                textDecoration: "none",
                "&:hover": {
                    borderColor: "primary.main",
                },
            }}
        >
            {/* Left side - Cover Image in Card */}
            <Card
                sx={{
                    width: coverWidth,
                    minWidth: coverWidth,
                    height: "100%",
                    flexShrink: 0,
                    borderRadius: 1.5,
                    overflow: "hidden",
                    boxShadow: 2,
                    position: "relative",
                }}
                component={RouterLink}
                to={`/reading-lists/${list.id}`}
            >
                {firstItemCover ? (
                    <CardMedia
                        component="img"
                        sx={{
                            height: "100%",
                            width: "100%",
                            objectFit: "cover",
                        }}
                        image={firstItemCover}
                        alt={`${list.title} cover`}
                    />
                ) : (
                    <Box
                        sx={{
                            height: "100%",
                            width: "100%",
                            background: defaultCoverBg,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                        }}
                    >
                        <BookIcon sx={{ fontSize: 40, color: "white" }} />
                    </Box>
                )}

                {/* Book count badge */}
                <Chip
                    icon={<BookIcon />}
                    label={`${list.items_count || 0}`}
                    size="small"
                    sx={{
                        position: "absolute",
                        top: 8,
                        right: 8,
                        backgroundColor: "rgba(0,0,0,0.6)",
                        backdropFilter: "blur(4px)",
                        color: "white",
                        fontWeight: "bold",
                        "& .MuiChip-icon": { color: "white", fontSize: "0.9rem" },
                    }}
                />
            </Card>

            {/* Right side - Content */}
            <Box
                sx={{
                    flexGrow: 1,
                    flexShrink: 1,
                    overflow: "hidden",
                    p: 2,
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    height: "100%",
                }}
            >
                {/* Title and description */}
                <Box>
                    <Typography
                        component={RouterLink}
                        to={`/reading-lists/${list.id}`}
                        variant="h6"
                        sx={{
                            fontWeight: 600,
                            mb: 0.5,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            display: "-webkit-box",
                            WebkitLineClamp: 1,
                            WebkitBoxOrient: "vertical",
                            color: "text.primary",
                            textDecoration: "none",
                            "&:hover": {
                                textDecoration: "underline",
                            },
                        }}
                    >
                        {list.title}
                    </Typography>

                    {list.description && (
                        <Typography
                            variant="body2"
                            color="text.secondary"
                            sx={{
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                display: "-webkit-box",
                                WebkitLineClamp: 2,
                                WebkitBoxOrient: "vertical",
                                mb: 1,
                            }}
                        >
                            {list.description}
                        </Typography>
                    )}
                </Box>

                {/* Footer with user and update time */}
                <Box
                    sx={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        mt: "auto",
                    }}
                >
                    {/* User info */}
                    <Box sx={{ display: "flex", alignItems: "center" }}>
                        <Avatar
                            sx={{
                                width: 24,
                                height: 24,
                                mr: 1,
                                bgcolor: "primary.main",
                                fontSize: "0.8rem",
                            }}
                            alt={list.user.username}
                            title={list.user.username}
                            src={list.user.profile_pic || undefined}
                        >
                            {list.user.username[0].toUpperCase()}
                        </Avatar>
                        <Typography variant="body2" color="text.secondary">
                            {list.user.username}
                        </Typography>
                    </Box>

                    {/* Update time */}
                    <Typography variant="caption" color="text.secondary">
                        {formatTimeAgo(new Date(list.updated_at))}
                    </Typography>
                </Box>
            </Box>
        </Box>
    );
};

export default ReadingListCard;
