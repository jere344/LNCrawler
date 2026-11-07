"""Admin action factories shared by the admin modules."""
from django.contrib import admin


def update_action(description, message, **updates):
    """Admin action that sets ``updates`` on the selected rows.

    ``message`` is formatted with the number of rows updated.
    """
    def action(modeladmin, request, queryset):
        updated = queryset.update(**updates)
        modeladmin.message_user(request, message.format(updated))

    return admin.action(description=description)(action)
