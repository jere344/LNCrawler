from rest_framework import serializers
from ..models.reviews_models import Review, ReviewReaction
from auth_app.serializers import OtherUserSerializer
from ..utils.ip_utils import get_client_ip


class ReactionSerializer(serializers.ModelSerializer):
    """Simplified serializer for reactions shown in review listings"""
    
    class Meta:
        model = ReviewReaction
        fields = ['id','reaction']
        read_only_fields = ['id']


class ReviewListSerializer(serializers.ModelSerializer):
    """Serializer for listing reviews with their reactions"""
    user = OtherUserSerializer(read_only=True)
    reactions = ReactionSerializer(many=True, read_only=True)
    novel_title = serializers.CharField(source='novel.title', read_only=True)
    novel_slug = serializers.CharField(source='novel.slug', read_only=True)
    reaction_count = serializers.IntegerField(source='get_reaction_count', read_only=True)
    current_user_reaction = serializers.SerializerMethodField()
    
    class Meta:
        model = Review
        fields = [
            'id', 'novel_title', 'novel_slug', 'user', 'title', 'content', 
            'rating', 'created_at', 'updated_at', 
            'reaction_count', 'reactions', 'current_user_reaction'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'reaction_count']
    
    def get_current_user_reaction(self, obj):
        """Get the current user's reaction to this review, if any"""
        request = self.context.get('request')
        if not request:
            return None

        # Use the prefetched reactions to avoid a query per review
        if request.user.is_authenticated:
            for reaction in obj.reactions.all():
                if reaction.user_id == request.user.id:
                    return ReactionSerializer(reaction).data
            return None

        # For anonymous users, check by IP address
        ip_address = get_client_ip(request)
        for reaction in obj.reactions.all():
            if reaction.user_id is None and reaction.ip_address == ip_address:
                return ReactionSerializer(reaction).data

        return None


class ReviewCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating reviews"""
    class Meta:
        model = Review
        fields = ['title', 'content', 'rating']
        
    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value


class ReactionCreateSerializer(serializers.ModelSerializer):
    """Serializer for adding reactions to reviews"""
    class Meta:
        model = ReviewReaction
        fields = ['reaction']
        
    def validate_reaction(self, value):
        valid_reactions = [choice[0] for choice in ReviewReaction.REACTION_CHOICES]
        if value not in valid_reactions:
            raise serializers.ValidationError(f"Invalid reaction. Must be one of: {valid_reactions}")
        return value

