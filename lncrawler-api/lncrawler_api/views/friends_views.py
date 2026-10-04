from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from ..models.users_models import Friendship
from ..serializers.profile_serializers import FriendshipSerializer
from ..utils.pagination import parse_page_size
from auth_app.serializers import OtherUserSerializer

User = get_user_model()

MAX_PENDING_FRIEND_REQUESTS = 50
MAX_FRIENDS_PER_REQUEST = 50


def friend_user_queryset(user):
    """Users who have an accepted friendship with ``user``."""
    return User.objects.filter(
        Q(friend_requests_sent__addressee=user,
          friend_requests_sent__status=Friendship.ACCEPTED)
        | Q(friend_requests_received__requester=user,
            friend_requests_received__status=Friendship.ACCEPTED)
    ).distinct()


def _friend_users(user, limit=None):
    friends = friend_user_queryset(user)
    if limit is not None:
        friends = friends[:limit]
    return list(friends)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_friends(request):
    """List the authenticated user's accepted friends.

    The frontend consumes a bare array (User[]), so we keep the response shape
    and cap the result via page_size instead of returning a paginated envelope.
    """
    limit = parse_page_size(request, default=MAX_FRIENDS_PER_REQUEST, max_size=MAX_FRIENDS_PER_REQUEST)
    serializer = OtherUserSerializer(
        _friend_users(request.user, limit=limit), many=True, context={"request": request}
    )
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_friend_requests(request):
    """List the authenticated user's friend requests: ?type=incoming (default) or outgoing."""
    direction = request.query_params.get("type", "incoming")
    if direction == "outgoing":
        friendships = Friendship.objects.filter(requester=request.user, status=Friendship.PENDING)
    else:
        friendships = Friendship.objects.filter(addressee=request.user, status=Friendship.PENDING)
    friendships = friendships.select_related('requester', 'addressee').order_by('-created_at')
    serializer = FriendshipSerializer(friendships, many=True, context={"request": request})
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_friend_request(request, username):
    """Send a friend request. A pending request in the other direction is
    accepted automatically (both sides clearly want it)."""
    target = get_object_or_404(User, username=username)
    if target.id == request.user.id:
        return Response({"detail": "You cannot add yourself."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            existing = Friendship.objects.filter(
                Q(requester=request.user, addressee=target) | Q(requester=target, addressee=request.user)
            ).select_for_update().first()
            if existing:
                if existing.status == Friendship.ACCEPTED:
                    return Response({"detail": "Already friends."}, status=status.HTTP_400_BAD_REQUEST)
                if existing.addressee_id == request.user.id:
                    existing.status = Friendship.ACCEPTED
                    existing.save(update_fields=['status', 'updated_at'])
                    return Response({"status": "accepted", "friendship_id": existing.id})
                return Response({"status": "request_sent", "friendship_id": existing.id})

            pending_count = Friendship.objects.filter(
                requester=request.user, status=Friendship.PENDING
            ).count()
            if pending_count >= MAX_PENDING_FRIEND_REQUESTS:
                return Response(
                    {"detail": "You have too many pending friend requests."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            friendship = Friendship.objects.create(requester=request.user, addressee=target)
    except IntegrityError:
        # Lost a concurrent send: the other direction won the unique-pair race.
        existing = Friendship.objects.filter(
            Q(requester=request.user, addressee=target) | Q(requester=target, addressee=request.user)
        ).first()
        if existing is None:
            return Response({"status": "request_sent", "friendship_id": None})
        if existing.status == Friendship.ACCEPTED:
            return Response({"detail": "Already friends."}, status=status.HTTP_400_BAD_REQUEST)
        if existing.addressee_id == request.user.id:
            existing.status = Friendship.ACCEPTED
            existing.save(update_fields=['status', 'updated_at'])
            return Response({"status": "accepted", "friendship_id": existing.id})
        return Response({"status": "request_sent", "friendship_id": existing.id})

    return Response({"status": "request_sent", "friendship_id": friendship.id}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def respond_friend_request(request, friendship_id):
    """Accept or decline an incoming request. Declining deletes the request."""
    action = request.data.get("action")
    if action not in ("accept", "decline"):
        return Response({"detail": "action must be 'accept' or 'decline'."}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        friendship = get_object_or_404(
            Friendship.objects.select_for_update(),
            id=friendship_id,
            addressee=request.user,
        )
        if friendship.status != Friendship.PENDING:
            return Response(
                {"detail": "This friend request is no longer pending."},
                status=status.HTTP_409_CONFLICT,
            )
        if action == "accept":
            friendship.status = Friendship.ACCEPTED
            friendship.save(update_fields=['status', 'updated_at'])
            return Response({"status": "accepted", "friendship_id": friendship.id})
        friendship.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_friend(request, username):
    """Unfriend someone, or cancel an outgoing request."""
    target = get_object_or_404(User, username=username)
    friendships = Friendship.objects.filter(
        Q(requester=request.user, addressee=target) | Q(requester=target, addressee=request.user)
    )
    deleted, _ = friendships.delete()
    if not deleted:
        return Response({"detail": "No friendship found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(status=status.HTTP_204_NO_CONTENT)
