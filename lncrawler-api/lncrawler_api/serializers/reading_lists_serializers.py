from rest_framework import serializers

from ..models.users_models import ReadingList, ReadingListItem, ReadingListCollaborator
from .users_serializers import UserSerializer
from .novels_serializers import NovelSerializer
from .mixins import ProfileFieldsMixin


def get_reading_list_role(reading_list, user):
    """Return owner/editor/reader for a user on a list, or None."""
    if not user or not user.is_authenticated:
        return None
    if reading_list.user_id == user.id:
        return 'owner'
    for collaborator in reading_list.collaborators.all():
        if collaborator.user_id == user.id:
            return collaborator.role
    return None


class ReadingListItemSerializer(serializers.ModelSerializer):
    novel = NovelSerializer(read_only=True, profile='card')
    novel_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = ReadingListItem
        fields = ['id', 'novel', 'novel_id', 'note', 'position', 'added_at']
        read_only_fields = ['id', 'added_at']


class ReadingListCollaboratorSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True, profile='compact')

    class Meta:
        model = ReadingListCollaborator
        fields = ['id', 'user', 'role', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class ReadingListSerializer(ProfileFieldsMixin, serializers.ModelSerializer):
    """
    Serializes a ReadingList through one of two profiles.

    ``card`` is the lightweight list (default, also the writable shape);
    ``detail`` swaps the summary fields (items_count / first_item /
    items_names) for the full ``items`` payload.
    """
    user = UserSerializer(read_only=True, profile='compact')
    user_role = serializers.SerializerMethodField()
    collaborators = ReadingListCollaboratorSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()
    first_item = serializers.SerializerMethodField()
    items_names = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()

    default_profile = 'card'
    field_profiles = {
        'card': [
            'id', 'title', 'description', 'is_public', 'user', 'user_role',
            'collaborators', 'items_count', 'created_at', 'updated_at',
            'first_item', 'items_names',
        ],
        'detail': [
            'id', 'title', 'description', 'is_public', 'user', 'user_role',
            'collaborators', 'items', 'created_at', 'updated_at',
        ],
    }

    class Meta:
        model = ReadingList
        read_only_fields = ['id', 'user', 'user_role', 'collaborators', 'created_at', 'updated_at']

    def get_user_role(self, obj):
        request = self.context.get('request')
        return get_reading_list_role(obj, getattr(request, 'user', None))

    def _visible_items(self, obj):
        # ``visible_items`` is prefetched (adult-filtered) by the list views.
        # Fall back to the manager for freshly created/updated instances.
        items = getattr(obj, 'visible_items', None)
        if items is None:
            items = list(obj.items.all())
        return items

    def get_items_count(self, obj):
        return len(self._visible_items(obj))

    def get_first_item(self, obj):
        items = self._visible_items(obj)
        if not items:
            return None
        return ReadingListItemSerializer(items[0], context=self.context).data

    def get_items_names(self, obj):
        return [item.novel.title for item in self._visible_items(obj) if item.novel]

    def get_items(self, obj):
        return ReadingListItemSerializer(
            self._visible_items(obj), many=True, context=self.context
        ).data
