"""The 0079 data migration puts LLM-failed tag clusters back to pending."""

import importlib
import uuid

from django.apps import apps
from django.test import TestCase
from django.utils import timezone

from ..models import TagCluster

migration = importlib.import_module(
    "lncrawler_api.migrations.0079_requeue_llm_failed_tag_clusters"
)


class RequeueLLMFailedClustersTests(TestCase):
    @staticmethod
    def _cluster(signature, status, error, **extra):
        return TagCluster.objects.create(
            signature=signature,
            tag_ids=[1, 2],
            tag_names=["a", "b"],
            status=status,
            error=error,
            **extra,
        )

    def test_resets_only_llm_content_errors(self):
        judged = {
            "llm_response": {"sets": []},
            "llm_batch": uuid.uuid4(),
            "judged_at": timezone.now(),
            "llm_model": "openai/gpt-oss-20b",
        }
        reset = [
            self._cluster("r1", TagCluster.STATUS_ERROR,
                          "no JSON object in LLM content: ''", **judged),
            self._cluster("r2", TagCluster.STATUS_ERROR,
                          "invalid JSON in LLM content: '{'", **judged),
            self._cluster("r3", TagCluster.STATUS_ERROR,
                          "LLM content is not a JSON object", requeue_count=2, **judged),
            self._cluster("r4", TagCluster.STATUS_ERROR,
                          "LLM answer has no 'groups' list", **judged),
        ]
        kept = [
            self._cluster("k1", TagCluster.STATUS_ERROR, "plan kept changing", requeue_count=3),
            self._cluster("k2", TagCluster.STATUS_ERROR, "MergeError: something else"),
            self._cluster("k3", TagCluster.STATUS_REVIEW, "LLM content is not a JSON object"),
            self._cluster("k4", TagCluster.STATUS_APPLIED, ""),
            self._cluster("k5", TagCluster.STATUS_REVIEW, "LLM answer has no 'groups' list"),
        ]

        migration.requeue_llm_failed_clusters(apps, None)

        for cluster in reset:
            cluster.refresh_from_db()
            self.assertEqual(cluster.status, TagCluster.STATUS_PENDING)
            self.assertEqual(cluster.requeue_count, 0)
            self.assertEqual(cluster.error, "")
            self.assertIsNone(cluster.llm_response)
            self.assertIsNone(cluster.llm_batch)
            self.assertIsNone(cluster.judged_at)

        expected = {"k1": (TagCluster.STATUS_ERROR, 3, "plan kept changing"),
                    "k2": (TagCluster.STATUS_ERROR, 0, "MergeError: something else"),
                    "k3": (TagCluster.STATUS_REVIEW, 0, "LLM content is not a JSON object"),
                    "k4": (TagCluster.STATUS_APPLIED, 0, ""),
                    "k5": (TagCluster.STATUS_REVIEW, 0, "LLM answer has no 'groups' list")}
        for cluster in kept:
            cluster.refresh_from_db()
            self.assertEqual(
                (cluster.status, cluster.requeue_count, cluster.error),
                expected[cluster.signature],
            )
