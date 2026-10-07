from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

MAX_AUTHOR_NAME_LENGTH = 100
MAX_MESSAGE_LENGTH = 10000


def resolve_author(request, author_name):
    """Return ``(user_or_None, display_name)`` for a submitted author.

    Authenticated requests are attributed to the logged-in user and their
    username always wins over any payload value. Anonymous requests must supply
    a non-empty name within the length limit, and may not use a registered
    username (anti-impersonation). Raises ``ValidationError`` on invalid input.
    """
    user = request.user if request.user.is_authenticated else None

    if author_name is not None:
        if not isinstance(author_name, str):
            raise ValidationError('Invalid author name')
        author_name = author_name.strip()

    if not author_name:
        if user:
            return user, user.username
        raise ValidationError('Author name is required for anonymous messages')

    if len(author_name) > MAX_AUTHOR_NAME_LENGTH:
        raise ValidationError(
            f'Author name must be at most {MAX_AUTHOR_NAME_LENGTH} characters'
        )

    if user is None and get_user_model().objects.filter(username__iexact=author_name).exists():
        raise ValidationError(
            'This name belongs to a registered user. Please log in or pick another name.'
        )

    return user, author_name
