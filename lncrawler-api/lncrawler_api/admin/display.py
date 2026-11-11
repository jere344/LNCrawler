"""Display helpers shared by the admin list and inline columns."""
from django.urls import reverse
from django.utils.html import format_html


def truncate(text, limit):
    """``text`` cut to ``limit`` characters, with "..." added when it was longer."""
    return text[:limit] + "..." if len(text) > limit else text


def comment_target(comment):
    """The novel or chapter a comment is on, as a label."""
    if comment.novel:
        return f"Novel: {comment.novel}"
    elif comment.chapter:
        return f"Chapter: {comment.chapter.display_title}"
    return "Unknown"


def parent_link(obj, change_url_name, top_level_text):
    """Link to the parent of ``obj``, or ``top_level_text`` when it has none."""
    if obj.parent:
        url = reverse(change_url_name, args=[obj.parent.id])
        return format_html('<a href="{}">{}</a>', url, f"Reply to: {obj.parent.author_name}")
    return top_level_text
