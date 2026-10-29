# Import all admin modules to ensure they are registered
from . import (
    audiobook_admin,
    author_merge_admin,
    candidate_admin,
    chat_admin,
    chapter_admin,
    comment_admin,
    cover_admin,
    csv_export,
    downloader_admin,
    harvest_admin,
    llm_admin,
    novel_admin,
    review_admin,
    scheduler_admin,
    source_admin,
    user_admin,
)

# Regroup the admin sidebar into categories (must come last).
from . import app_groups  # noqa: E402,F401