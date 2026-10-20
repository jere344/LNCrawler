"""Cover and overview image generation.

Extracted from the former ``generate_overview`` / ``generate_cover_min``
management commands. The logic runs automatically when a source is imported
(see ``NovelFromSource.generate_overview_image`` / ``generate_cover_min``), so
it lives here as plain callables rather than management commands.
"""
