from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from lncrawler_api.models import Novel
from lncrawler_api.models.comments_models import Comment


class Command(BaseCommand):
    help = 'Recalculates the comment count for all novels'

    def handle(self, *args, **options):
        # Get all novels
        novels = Novel.objects.all()
        
        self.stdout.write(self.style.SUCCESS(f'Starting comment count recalculation for {novels.count()} novels...'))
        
        updated_count = 0
        for novel in novels:
            # Count direct comments on novel
            direct_comments = Comment.objects.filter(novel=novel).count()
            
            # Count comments on chapters from all sources of this novel
            chapter_ids = []
            for source in novel.sources.all():
                chapter_ids.extend(source.chapters.values_list('id', flat=True))
            
            chapter_comments = Comment.objects.filter(chapter_id__in=chapter_ids).count()
            
            # Total comments
            total_comments = direct_comments + chapter_comments
            
            # Update only if the count has changed
            if novel.comment_count != total_comments:
                novel.comment_count = total_comments
                novel.save(update_fields=['comment_count'])
                updated_count += 1
                self.stdout.write(f'Updated "{novel.title}": {novel.comment_count} comments')
                
        self.stdout.write(self.style.SUCCESS(f'Comment count recalculation complete. Updated {updated_count} novels.'))
