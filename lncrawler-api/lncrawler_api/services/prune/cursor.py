"""Phase cursor, verdicts and the bounded candidate window."""

import os

from django.db.models import CharField
from django.db.models.functions import Cast, MD5, Substr

from lncrawler_api.utils.atomic_json import load_json, write_json_atomic

from .common import VERDICTS_FILE


class CursorMixin:
    def _load_cursor(self) -> dict:
        return load_json(os.path.join(self.trash_root, "prune_cursor.json"), {})

    def _save_cursor(self):
        if not self.apply:
            return
        os.makedirs(self.trash_root, exist_ok=True)
        write_json_atomic(os.path.join(self.trash_root, "prune_cursor.json"), self.cursor)

    def _verdicts_path(self):
        return os.path.join(self.trash_root, VERDICTS_FILE)

    def _load_verdicts(self) -> dict:
        return load_json(self._verdicts_path(), {})

    def _save_verdicts(self):
        if not self.apply:
            return
        os.makedirs(self.trash_root, exist_ok=True)
        write_json_atomic(self._verdicts_path(), self.verdicts)

    def _cursor_key(self, phase):
        return f"{phase}:{self.cursor_scope}"

    def _window(self, queryset, phase, order="pk"):
        """Return the next batch of candidates, continuing from the saved cursor.

        Candidates are walked in ``order``; if ``--limit`` is set only that many
        are fetched, starting after the last pk seen for this phase. The cursor
        is updated by ``_advance`` once the batch is processed.
        """
        queryset = queryset.order_by(order)
        if not self.limit:
            return queryset
        start = self.cursor.get(self._cursor_key(phase))
        if start is not None:
            queryset = queryset.filter(**{f"{order}__gt": start})
        return queryset[: self.limit]

    def _advance(self, phase, last_pk, examined):
        """Record how far this phase got, wrapping to the start after a pass."""
        self.examined += examined
        if not self.limit:
            return
        key = self._cursor_key(phase)
        if examined < self.limit:
            self.cursor.pop(key, None)
        elif last_pk is not None:
            self.cursor[key] = last_pk if isinstance(last_pk, int) else str(last_pk)
        self._save_cursor()

    def _sample(self, queryset, field="id"):
        """Keep an MD5-bucket slice of the rows, so --percent N examines ~N%.

        Keys are UUIDs, so hash the key to a uniform hex bucket instead of
        sorting randomly: the subset is stable across runs. The bucket is a
        computed predicate, so it cannot use an index.
        """
        if self.percent >= 100:
            return queryset
        bucket = Substr(MD5(Cast(field, CharField())), 1, 2)
        threshold = format(int(self.percent / 100 * 256), "02x")
        return queryset.annotate(_bucket=bucket).filter(_bucket__lt=threshold)
