from django.contrib import admin
from django.utils.text import slugify

# Sidebar/dashboard categories for the single lncrawler_api app. All models live
# in one Django app, so by default they show up as one huge list. We regroup the
# app list into fake "apps" (categories) without moving any model.
# Add a model name to a group to place it; anything unlisted stays under the
# original lncrawler_api app.
APP_GROUPS = [
    (
        "Novels",
        [
            "Novel",
            "MergeCandidate",
            "NovelAlias",
            "NovelSimilarity",
            "NovelRating",
            "FeaturedNovel",
            "WeeklySourceView",
        ],
    ),
    ("Chapters & Volumes", ["Chapter", "Volume"]),
    ("Authors, Tags & Translators", ["Author", "Editor", "Translator", "Tag", "TagAlias"]),
    ("Sources", ["ExternalSource", "NovelFromSource", "SourceVote"]),
    (
        "Community",
        ["Review", "ReviewReaction", "Comment", "CommentVote", "ChatMessage"],
    ),
    ("Profiles & Social", ["Friendship", "ProfilePinnedNovel"]),
    ("Harvesting", ["HarvestCandidate", "HarvestConfig"]),
    ("Jobs & Scheduler", ["Job", "ScheduledTask"]),
]

_GROUP_OF = {model: name for name, models in APP_GROUPS for model in models}

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
        if app["app_label"] != "lncrawler_api":
            rest.append(app)
            continue
        leftover = []
        for model in app["models"]:
            name = _GROUP_OF.get(model["object_name"])
            if name is None:
                leftover.append(model)
            else:
                grouped.setdefault(name, []).append(model)
        if leftover:
            rest.append({**app, "models": leftover})

    result = []
    for name, _models in APP_GROUPS:
        models = grouped.get(name)
        if not models:
            continue
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
