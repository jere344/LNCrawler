from django.core.management.base import BaseCommand, CommandError

from lncrawler_api.models import Tag
from lncrawler_api.services import MergeError, merge_similar_tags, merge_tags


class Command(BaseCommand):
    help = (
        'Merge two tags, or auto-merge trivially similar tags '
        '(case, plural, near-typo) when no names are given'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'source_tag',
            nargs='?',
            help='Name of the duplicate tag (deleted after merge)',
        )
        parser.add_argument(
            'target_tag',
            nargs='?',
            help='Name of the canonical tag (kept)',
        )
        parser.add_argument(
            '--auto',
            action='store_true',
            help='Auto-merge all trivially similar tags instead of a named pair',
        )
        parser.add_argument(
            '--threshold',
            type=float,
            default=None,
            help='Similarity threshold for --auto (default: service default)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be merged without changing anything',
        )

    def handle(self, *args, **options):
        auto = options['auto'] or not (options['source_tag'] and options['target_tag'])

        if auto:
            kwargs = {'dry_run': options['dry_run']}
            if options['threshold'] is not None:
                kwargs['threshold'] = options['threshold']
            results = merge_similar_tags(**kwargs)
            if not results:
                self.stdout.write('No similar tags found.')
                return
            for survivor, duplicates in results:
                self.stdout.write(
                    f"  {'would merge' if options['dry_run'] else 'merged'} "
                    f"{', '.join(duplicates)} -> {survivor}"
                )
            if options['dry_run']:
                self.stdout.write(self.style.WARNING('DRY RUN - no changes made'))
            return

        try:
            source = Tag.objects.get(name=options['source_tag'])
        except Tag.DoesNotExist:
            raise CommandError(f"Tag '{options['source_tag']}' not found")
        try:
            target = Tag.objects.get(name=options['target_tag'])
        except Tag.DoesNotExist:
            raise CommandError(f"Tag '{options['target_tag']}' not found")

        self.stdout.write(f"Merging tag '{source.name}' into '{target.name}'")
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes made'))
            return

        try:
            merge_tags(source, target)
        except MergeError as e:
            raise CommandError(str(e))

        self.stdout.write(self.style.SUCCESS(
            f"Successfully merged '{source.name}' into '{target.name}'."
        ))
