import logging

from django.core.management.base import BaseCommand, CommandError

from lncrawler_api.models import Novel
from lncrawler_api.services import MergeError, build_merge_plan, merge_novels

logger = logging.getLogger('lncrawler_api')


class Command(BaseCommand):
    help = 'Merge two novels by moving all sources from the source novel to the target novel'

    def add_arguments(self, parser):
        parser.add_argument(
            'source_slug',
            type=str,
            help='Slug of the source novel (will be deleted after merge)'
        )
        parser.add_argument(
            'target_slug',
            type=str,
            help='Slug of the target novel (will receive all sources)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually performing the merge'
        )
        parser.add_argument(
            '--move-files',
            action='store_true',
            default=True,
            help='Also move the physical source folders to the target novel folder (default: True)'
        )
        parser.add_argument(
            '--no-move-files',
            action='store_false',
            dest='move_files',
            help='Do not move the physical source folders'
        )

    def handle(self, *args, **options):
        source_slug = options['source_slug']
        target_slug = options['target_slug']
        dry_run = options['dry_run']
        move_files = options['move_files']

        try:
            source_novel = Novel.objects.get(slug=source_slug)
        except Novel.DoesNotExist:
            raise CommandError(f"Source novel with slug '{source_slug}' not found")

        try:
            target_novel = Novel.objects.get(slug=target_slug)
        except Novel.DoesNotExist:
            raise CommandError(f"Target novel with slug '{target_slug}' not found")

        try:
            plan = build_merge_plan(source_novel, target_novel, move_files)
        except MergeError as e:
            raise CommandError(str(e))

        self.stdout.write(
            f"Merging '{source_novel.title}' ({source_novel.slug}) into "
            f"'{target_novel.title}' ({target_novel.slug})"
        )
        for source_plan in plan.sources:
            if source_plan.action == "move":
                self.stdout.write(f"  move   {source_plan.source.title}")
            else:
                self.stdout.write(
                    f"  dedupe {source_plan.source.title} -> keep "
                    f"{source_plan.winner.title}"
                )
        for slug in plan.alias_slugs:
            self.stdout.write(f"  alias  {slug} -> {target_novel.slug}")
        for warning in plan.warnings:
            self.stdout.write(self.style.WARNING(f"  warning: {warning}"))

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes made"))
            return

        try:
            merge_novels(source_novel, target_novel, move_files=move_files)
        except MergeError as e:
            raise CommandError(str(e))

        self.stdout.write(self.style.SUCCESS(
            f"Successfully merged '{source_novel.title}' into '{target_novel.title}'."
        ))
