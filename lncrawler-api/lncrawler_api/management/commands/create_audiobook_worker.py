"""
Create an audiobook worker account, or rotate its token.

The user is created with an unusable password when missing and added to the audiobook_workers group.
Its DRF token is created when missing and replaced with --rotate. The token is printed only when it is
created or rotated: keep it, it cannot be read again. Run again without --rotate, the token is left alone.
"""

from django.core.management.base import BaseCommand

from ...services.audiobook_worker_auth import WORKER_GROUP, ensure_worker_token


class Command(BaseCommand):
    help = "Create an audiobook worker user with its API token (or rotate the token with --rotate)."

    def add_arguments(self, parser):
        parser.add_argument('username', help="Username of the worker account")
        parser.add_argument(
            '--rotate', action='store_true',
            help="Replace the token: the previous one stops working",
        )

    def handle(self, *args, **options):
        username = options['username']
        key, created = ensure_worker_token(username, rotate=options['rotate'])
        if options['rotate']:
            action = "rotated"
        else:
            action = "created" if created else "already exists, token unchanged (use --rotate to get a new one)"
        self.stdout.write(f"Worker {username} in group {WORKER_GROUP}: token {action}.")
        if options['rotate'] or created:
            self.stdout.write(f"Token: {key}")
