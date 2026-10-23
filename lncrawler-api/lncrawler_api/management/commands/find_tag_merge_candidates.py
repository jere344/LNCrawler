"""Find groups of possibly-duplicate tags and queue them for LLM judging.

Stage 1 of automatic tag merging. Embeds tag names that lack a current vector,
then combines three signals (embedding neighbours, cross-source co-occurrence,
trigram similarity) into clusters stored as pending ``tag_merge`` candidates. Nothing
is merged here; ``TagMergeTask`` decides, through the ``run_llm`` command.
Re-running is safe: a group that was already stored, in any status, is skipped by its signature.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from lncrawler_api.models import Candidate, NovelFromSource
from lncrawler_api.services import tag_merge_service as tms
from lncrawler_api.services.candidate_blocks import blocked_pairs


class Command(BaseCommand):
    help = "Embed new tags and queue clusters of possibly-duplicate tags for LLM judging."

    def add_arguments(self, parser):
        parser.add_argument("--skip-embed", action="store_true",
                            help="Do not call the embeddings API; use stored vectors only.")

    def handle(self, *args, **options):
        if not options["skip_embed"]:
            embedded = tms.embed_missing()
            self.stdout.write(f"embedded {embedded} tag(s)")

        ids, matrix = tms.load_embeddings()
        embed = tms.embedding_edges(
            ids, matrix, top_k=settings.EMBED_TOP_K, min_cos=settings.EMBED_MIN
        )

        cooc_rows = (
            NovelFromSource.tags.through.objects.order_by()
            .values_list("novelfromsource_id", "tag_id", "novelfromsource__novel_id")
            .iterator(chunk_size=20000)
        )
        cooc = tms.cooccurrence_edges(
            cooc_rows,
            min_novels=settings.TAG_COOC_MIN_NOVELS,
            min_ratio=settings.TAG_COOC_MIN,
            top_k=settings.TAG_COOC_TOP_K,
        )

        trgm = tms.trigram_edges(settings.TAG_TRGM_MIN)

        edges = tms.merge_signal_edges(embed=embed, cooc=cooc, trgm=trgm)
        blocked = blocked_pairs(Candidate.KIND_TAG_MERGE)
        clusters = tms.build_clusters(
            edges, max_size=settings.TAG_CLUSTER_MAX, blocked=blocked
        )

        created = tms.store_clusters(clusters)
        self.stdout.write(self.style.SUCCESS(
            f"tag candidates: {len(edges)} pair(s) "
            f"(embed {len(embed)}, cooc {len(cooc)}, trigram {len(trgm)}), "
            f"{len(clusters)} cluster(s), {created} new"
        ))
