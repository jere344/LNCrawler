from django.contrib import admin
from django.utils.text import slugify

# Sidebar/dashboard categories. All models live in the lncrawler_api app (CustomUser
# lives in auth_app), so by default they show up as one huge list. We regroup the
# app list into fake "apps" (categories) without moving any model.
# Add a model's object_name to a group to place it, from any app; anything unlisted
# stays under its original app block, after the groups.
APP_GROUPS = [
    ("Operations", ["HarvestConfig", "HarvestCandidate", "Job"]),
    ("Review", ["Candidate", "LLMCall"]),
    (
        "Library",
        [
            "Novel", "NovelAlias", "NovelFromSource", "Chapter", "Volume",
            "ExternalSource", "PlaceholderCover",
        ],
    ),
    (
        "People & Tags",
        ["Author", "AuthorAlias", "Editor", "Translator", "Tag", "TagAlias"],
    ),
    (
        "Community",
        [
            "CustomUser", "Comment", "CommentVote", "Review", "ReviewReaction",
            "ChatMessage", "SourceVote", "Friendship", "ProfilePinnedNovel",
        ],
    ),
    (
        "Audiobooks",
        [
            "Audiobook", "AudiobookPart", "AudiobookWorker", "ListeningProgress",
            "AudiobookDailyStat",
        ],
    ),
    ("Stats", ["NovelRating", "WeeklySourceView", "NovelSimilarity"]),
]

# Sidebar labels that differ from the model's verbose name.
DISPLAY_NAMES = {
    "CustomUser": "Users",
}

_GROUP_OF = {model: name for name, models in APP_GROUPS for model in models}
_POSITION_IN_GROUP = {
    model: position for _name, models in APP_GROUPS for position, model in enumerate(models)
}

_original_get_app_list = admin.site.get_app_list


def _grouped_get_app_list(request, app_label=None):
    app_list = _original_get_app_list(request, app_label)

    # Only the main index/sidebar (no app_label filter) is regrouped, so the
    # per-app index view keeps working with the real app_label.
    if app_label is not None:
        return app_list

    grouped = {}
    rest = []
    for app in app_list:
        leftover = []
        for model in app["models"]:
            name = _GROUP_OF.get(model["object_name"])
            if name is None:
                leftover.append(model)
            else:
                label = DISPLAY_NAMES.get(model["object_name"], model["name"])
                grouped.setdefault(name, []).append({**model, "name": label})
        if leftover:
            rest.append({**app, "models": leftover})

    result = []
    for name, _models in APP_GROUPS:
        models = grouped.get(name)
        if not models:
            continue
        models.sort(key=lambda model: _POSITION_IN_GROUP[model["object_name"]])
        app_url = next((m["admin_url"] for m in models if m["admin_url"]), "")
        result.append(
            {
                "name": name,
                "app_label": slugify(name),
                "app_url": app_url,
                "has_module_perms": True,
                "models": models,
            }
        )

    return result + rest


admin.site.get_app_list = _grouped_get_app_list
