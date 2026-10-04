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
from auth_app.serializers import OtherUserSerializer

User = get_user_model()


def _friend_users(user):
    friendships = (
        Friendship.objects
        .filter(status=Friendship.ACCEPTED)
        .filter(Q(requester=user) | Q(addressee=user))
        .select_related('requester', 'addressee')
    )
    return [
        f.addressee if f.requester_id == user.id else f.requester
        for f in friendships
    ]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_friends(request):
    """List the authenticated user's accepted friends."""
    serializer = OtherUserSerializer(_friend_users(request.user), many=True, context={"request": request})
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
    friendship = get_object_or_404(Friendship, id=friendship_id, addressee=request.user)
    action = request.data.get("action")
    if action == "accept":
        friendship.status = Friendship.ACCEPTED
        friendship.save(update_fields=['status', 'updated_at'])
        return Response({"status": "accepted", "friendship_id": friendship.id})
    if action == "decline":
        friendship.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    return Response({"detail": "action must be 'accept' or 'decline'."}, status=status.HTTP_400_BAD_REQUEST)


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
