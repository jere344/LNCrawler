from django.core.management.base import BaseCommand
from django.db import transaction
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict
from ...models import Novel, NovelBookmark, NovelSimilarity, NovelFromSource, Tag, Author

class Command(BaseCommand):
    help = 'Calculate similarity scores between novels'
    
    def add_arguments(self, parser):
        parser.add_argument('--text-weight', type=float, default=0.7, help='Weight for text-based similarity (0-1)')
        parser.add_argument('--bookmark-weight', type=float, default=0.3, help='Weight for bookmark-based similarity (0-1)')
    
    def handle(self, *args, **kwargs):
        text_weight = kwargs['text_weight']
        bookmark_weight = kwargs['bookmark_weight']
        
        if text_weight + bookmark_weight != 1.0:
            self.stdout.write(self.style.WARNING('Weights should sum to 1.0, normalizing...'))
            total = text_weight + bookmark_weight
            text_weight /= total
            bookmark_weight /= total
        
        self.stdout.write('Starting similarity calculation...')
        self.calculate_similarities(text_weight, bookmark_weight)
        self.stdout.write(self.style.SUCCESS('Successfully calculated similarities'))
    
    def calculate_similarities(self, text_weight, bookmark_weight):
        # Get all novels
        novels = Novel.objects.all()
        novel_count = novels.count()
        
        if novel_count == 0:
            self.stdout.write(self.style.WARNING('No novels found'))
            return
        
        self.stdout.write(f'Processing {novel_count} novels')
        
        # Create rich text representations for TF-IDF using tags, authors, and synopsis
        novel_texts = self.gather_novel_metadata(novels)
        
        # Calculate text similarities using TF-IDF
        self.stdout.write('Calculating text-based similarities...')
        text_similarities = self.calculate_text_similarities(novel_texts)
        
        # Calculate bookmark-based similarities
        self.stdout.write('Calculating bookmark-based similarities...')
        bookmark_similarities = self.calculate_bookmark_similarities(novels)
        
        # Combine similarities (weighted average)
        self.stdout.write('Combining similarities...')
        combined_similarities = self.combine_similarities(
            text_similarities, 
            bookmark_similarities, 
            text_weight, 
            bookmark_weight
        )
        
        # Save to database
        self.stdout.write('Saving similarities to database...')
        self.save_similarities(combined_similarities)
    
    def gather_novel_metadata(self, novels):
        """
        Gather rich metadata for each novel by combining data from all its sources
        """
        novel_texts = {}
        
        for novel in novels:
            # Get all sources for this novel
            sources = NovelFromSource.objects.filter(novel=novel).prefetch_related('tags', 'authors')
            
            if not sources:
                # If no sources, just use the title
                novel_texts[novel.id] = novel.title
                continue
                
            # Collect all unique tags from all sources
            all_tags = set()
            for source in sources:
                all_tags.update(tag.name for tag in source.tags.all())
            
            # Collect all unique authors from all sources
            all_authors = set()
            for source in sources:
                all_authors.update(author.name for author in source.authors.all())
            
            # Collect all synopses (might contain duplicate content, but that's fine for TF-IDF)
            all_synopses = [source.synopsis for source in sources if source.synopsis]
            
            # Combine all metadata with importance weighting (repeat important items)
            # Title is most important, followed by tags and authors, then synopsis
            combined_text = (
                # Title (repeated for emphasis)
                f"{novel.title} {novel.title} {novel.title} " +
                # Tags (repeated for emphasis)
                " ".join(f"{tag} {tag}" for tag in all_tags) + " " +
                # Authors (repeated for emphasis)
                " ".join(f"{author} {author}" for author in all_authors) + " " +
                # Synopsis (lower emphasis)
                " ".join(all_synopses)
            )
            
            novel_texts[novel.id] = combined_text
            
        return novel_texts
    
    def calculate_text_similarities(self, novel_texts):
        # Create TF-IDF matrix
        tfidf_vectorizer = TfidfVectorizer(max_features=5000, stop_words='english')
        
        # Get novel IDs and texts in the same order
        novel_ids = list(novel_texts.keys())
        texts = [novel_texts[nid] for nid in novel_ids]
        
        if not texts:
            return {}
        
        # Calculate TF-IDF
        tfidf_matrix = tfidf_vectorizer.fit_transform(texts)
        
        # Calculate cosine similarities
        cosine_sim = cosine_similarity(tfidf_matrix)
        
        # Convert to dictionary format
        similarities = {}
        for i, from_id in enumerate(novel_ids):
            similarities[from_id] = {}
            for j, to_id in enumerate(novel_ids):
                if i != j:  # Skip self-similarities
                    similarities[from_id][to_id] = float(cosine_sim[i][j])
        
        return similarities
    
    def calculate_bookmark_similarities(self, novels):
        # Get all bookmarks
        bookmarks = NovelBookmark.objects.all()
        
        # Create user-novel matrix
        user_novel_dict = defaultdict(set)
        novel_user_dict = defaultdict(set)
        
        for bookmark in bookmarks:
            user_novel_dict[bookmark.user_id].add(bookmark.novel_id)
            novel_user_dict[bookmark.novel_id].add(bookmark.user_id)
        
        # Calculate cosine similarity between novels based on bookmarks
        similarities = {}
        novel_ids = [novel.id for novel in novels]
        
        for i, from_id in enumerate(novel_ids):
            similarities[from_id] = {}
            from_users = novel_user_dict[from_id]
            
            for j, to_id in enumerate(novel_ids):
                if i != j:  # Skip self-similarities
                    to_users = novel_user_dict[to_id]
                    
                    # Calculate Jaccard similarity
                    if not from_users or not to_users:
                        similarities[from_id][to_id] = 0.0
                    else:
                        intersection = len(from_users.intersection(to_users))
                        union = len(from_users.union(to_users))
                        similarities[from_id][to_id] = intersection / union if union > 0 else 0.0
        
        return similarities
    
    def combine_similarities(self, text_similarities, bookmark_similarities, text_weight, bookmark_weight):
        # Combine the two similarity measures with weights
        combined = {}
        all_novel_ids = set(list(text_similarities.keys()) + list(bookmark_similarities.keys()))
        
        for from_id in all_novel_ids:
            combined[from_id] = {}
            for to_id in all_novel_ids:
                if from_id != to_id:
                    text_sim = text_similarities.get(from_id, {}).get(to_id, 0.0)
                    bookmark_sim = bookmark_similarities.get(from_id, {}).get(to_id, 0.0)
                    
                    # If we have both, do weighted average
                    if text_sim > 0 or bookmark_sim > 0:
                        combined[from_id][to_id] = text_weight * text_sim + bookmark_weight * bookmark_sim
                    else:
                        combined[from_id][to_id] = 0.0
        
        return combined
    
    @transaction.atomic
    def save_similarities(self, similarities):
        # Clear existing similarities
        NovelSimilarity.objects.all().delete()
        
        # Create batch of objects to insert
        similarity_objects = []
        batch_size = 1000
        count = 0
        processed = 0
        
        for from_id, to_sims in similarities.items():
            # Sort by similarity score in descending order
            sorted_sims = sorted(to_sims.items(), key=lambda x: x[1], reverse=True)
            
            # Get top 12 similar novels
            for to_id, score in sorted_sims[:12]:
                try:
                    from_novel = Novel.objects.get(pk=from_id)
                    to_novel = Novel.objects.get(pk=to_id)
                    
                    similarity_objects.append(NovelSimilarity(
                        from_novel=from_novel,
                        to_novel=to_novel,
                        similarity=score
                    ))
                    
                    count += 1
                    processed += 1
                    
                    # Insert in batches
                    if count >= batch_size:
                        NovelSimilarity.objects.bulk_create(similarity_objects)
                        similarity_objects = []
                        count = 0
                        self.stdout.write(f'Processed {processed} similarities')
                except Novel.DoesNotExist:
                    continue
        
        # Insert any remaining objects
        if similarity_objects:
            NovelSimilarity.objects.bulk_create(similarity_objects)
            self.stdout.write(f'Processed {processed} similarities')
