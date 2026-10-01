from collections import defaultdict

import numpy as np
from django.core.management.base import BaseCommand
from django.db import transaction
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

from ...models import (
    Author,
    Novel,
    NovelBookmark,
    NovelFromSource,
    NovelSimilarity,
    Tag,
)

TOP_K = 12


class Command(BaseCommand):
    help = 'Calculate similarity scores between novels'

    def add_arguments(self, parser):
        parser.add_argument('--text-weight', type=float, default=0.7, help='Weight for text-based similarity (0-1)')
        parser.add_argument('--bookmark-weight', type=float, default=0.3, help='Weight for bookmark-based similarity (0-1)')
        parser.add_argument('--chunk-size', type=int, default=512, help='Rows of the similarity matrix computed at once (memory knob)')
        parser.add_argument('--batch-size', type=int, default=2000, help='NovelSimilarity rows per bulk_create')

    def handle(self, *args, **kwargs):
        text_weight = kwargs['text_weight']
        bookmark_weight = kwargs['bookmark_weight']
        chunk_size = max(1, kwargs['chunk_size'])
        batch_size = max(1, kwargs['batch_size'])

        if text_weight + bookmark_weight != 1.0:
            self.stdout.write(self.style.WARNING('Weights should sum to 1.0, normalizing...'))
            total = text_weight + bookmark_weight
            text_weight /= total
            bookmark_weight /= total

        self.stdout.write('Starting similarity calculation...')
        self.calculate_similarities(text_weight, bookmark_weight, chunk_size, batch_size)
        self.stdout.write(self.style.SUCCESS('Successfully calculated similarities'))

    def calculate_similarities(self, text_weight, bookmark_weight, chunk_size, batch_size):
        novel_rows = list(Novel.objects.order_by('id').values_list('id', 'title'))
        if not novel_rows:
            self.stdout.write(self.style.WARNING('No novels found'))
            return

        novel_ids = [row[0] for row in novel_rows]
        title_by_id = dict(novel_rows)
        novel_count = len(novel_ids)
        del novel_rows
        self.stdout.write(f'Processing {novel_count} novels')

        texts = self.gather_novel_metadata(novel_ids, title_by_id)
        self.stdout.write('Fitting TF-IDF and normalizing...')
        tfidf_matrix = TfidfVectorizer(max_features=5000, stop_words='english').fit_transform(texts)
        del texts

        self.stdout.write('Building bookmark matrix...')
        bookmark_matrix, bookmark_counts = self.build_bookmark_matrix(novel_ids)

        self.save_similarities(
            novel_ids, tfidf_matrix, bookmark_matrix, bookmark_counts,
            text_weight, bookmark_weight, chunk_size, batch_size,
        )

    def gather_novel_metadata(self, novel_ids, title_by_id):
        """
        Build one text blob per novel in a constant number of queries.

        Tags/authors/synopses are aggregated in bulk keyed by novel id instead of
        one query per novel (the old N+1).
        """
        tags_by_novel = defaultdict(list)
        for novel_id, name in (
            Tag.objects.filter(novels__isnull=False)
            .values_list('novels__novel_id', 'name')
            .distinct()
            .iterator()
        ):
            tags_by_novel[novel_id].append(name)

        authors_by_novel = defaultdict(list)
        for novel_id, name in (
            Author.objects.filter(novels__isnull=False)
            .values_list('novels__novel_id', 'name')
            .distinct()
            .iterator()
        ):
            authors_by_novel[novel_id].append(name)

        synopses_by_novel = defaultdict(list)
        for novel_id, synopsis in (
            NovelFromSource.objects.values_list('novel_id', 'synopsis').iterator()
        ):
            if synopsis:
                synopses_by_novel[novel_id].append(synopsis)

        texts = []
        for novel_id in novel_ids:
            title = title_by_id[novel_id]
            tags = " ".join(f"{tag} {tag}" for tag in tags_by_novel.get(novel_id, ()))
            authors = " ".join(f"{author} {author}" for author in authors_by_novel.get(novel_id, ()))
            synopses = " ".join(synopses_by_novel.get(novel_id, ()))
            texts.append(f"{title} {title} {title} " + tags + " " + authors + " " + synopses)
        return texts

    def build_bookmark_matrix(self, novel_ids):
        """
        Sparse binary novels x users matrix.  Jaccard between novels is derived
        from A @ A.T plus per-row user counts.
        """
        index_of = {novel_id: i for i, novel_id in enumerate(novel_ids)}
        user_index = {}
        rows = []
        cols = []
        for novel_id, user_id in NovelBookmark.objects.values_list('novel_id', 'user_id').iterator():
            row = index_of.get(novel_id)
            if row is None:
                continue
            col = user_index.get(user_id)
            if col is None:
                col = len(user_index)
                user_index[user_id] = col
            rows.append(row)
            cols.append(col)

        if not rows:
            return None, None

        data = np.ones(len(rows), dtype=np.float32)
        matrix = sparse.csr_matrix(
            (data, (rows, cols)), shape=(len(novel_ids), len(user_index)), dtype=np.float32
        )
        counts = np.asarray(matrix.sum(axis=1)).ravel().astype(np.float32)
        return matrix, counts

    def combined_block(self, tfidf_matrix, bookmark_matrix, bookmark_counts,
                       start, end, text_weight, bookmark_weight):
        """
        Dense (chunk x N) weighted similarity block for [start, end).

        Peak memory is O((end - start) * N), never O(N^2).
        """
        chunk = tfidf_matrix[start:end]
        block = (chunk @ tfidf_matrix.T).toarray().astype(np.float32, copy=False)
        np.multiply(block, text_weight, out=block)

        if bookmark_matrix is not None and bookmark_matrix.nnz:
            intersection = (bookmark_matrix[start:end] @ bookmark_matrix.T).toarray().astype(np.float32, copy=False)
            from_counts = bookmark_counts[start:end][:, None]
            to_counts = bookmark_counts[None, :]
            union = from_counts + to_counts - intersection
            np.divide(intersection, union, out=intersection, where=union > 0)
            intersection *= bookmark_weight
            block += intersection

        return block

    @transaction.atomic
    def save_similarities(self, novel_ids, tfidf_matrix, bookmark_matrix, bookmark_counts,
                          text_weight, bookmark_weight, chunk_size, batch_size):
        NovelSimilarity.objects.all().delete()

        novel_count = len(novel_ids)
        top_k = min(TOP_K, max(0, novel_count - 1))

        buffer = []
        processed = 0
        for start in range(0, novel_count, chunk_size):
            end = min(start + chunk_size, novel_count)
            block = self.combined_block(
                tfidf_matrix, bookmark_matrix, bookmark_counts,
                start, end, text_weight, bookmark_weight,
            )

            if top_k:
                for local, from_index in enumerate(range(start, end)):
                    row = block[local]
                    row[from_index] = -np.inf  # exclude self (global column index)
                    candidates = np.argpartition(row, -top_k)[-top_k:]
                    candidates = candidates[np.argsort(row[candidates])[::-1]]
                    from_id = novel_ids[from_index]
                    for to_index in candidates:
                        score = float(row[to_index])
                        if score < 0.0:
                            score = 0.0
                        buffer.append(NovelSimilarity(
                            from_novel_id=from_id,
                            to_novel_id=novel_ids[to_index],
                            similarity=score,
                        ))

            if len(buffer) >= batch_size:
                NovelSimilarity.objects.bulk_create(buffer, batch_size=batch_size)
                processed += len(buffer)
                buffer = []
                self.stdout.write(f'Processed {processed} similarities')

            del block

        if buffer:
            NovelSimilarity.objects.bulk_create(buffer, batch_size=batch_size)
            processed += len(buffer)
            self.stdout.write(f'Processed {processed} similarities')
