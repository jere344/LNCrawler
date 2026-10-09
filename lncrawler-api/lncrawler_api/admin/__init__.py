# Import all admin modules to ensure they are registered
from . import (
    chat_admin,
    chapter_admin,
    comment_admin,
    downloader_admin,
    harvest_admin,
    merge_admin,
    novel_admin,
    review_admin,
    scheduler_admin,
    source_admin,
    user_admin,
)

# Regroup the admin sidebar into categories (must come last).
from . import app_groups  # noqa: E402,F401