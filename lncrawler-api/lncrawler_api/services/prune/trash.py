"""Moving deleted source folders to the trash and writing the audit log."""

import json
import os
import shutil
from datetime import datetime

from lncrawler_api.models.source_helpers import resolve_output_path

from .common import logger


class TrashMixin:
    def _move_to_trash(self, rel):
        """Move a source folder under ``.prune_trash``; returns the new path or None.

        ``rel`` comes from the DB, so it is resolved the same way the model
        resolves it, and refused unless it lies strictly inside the library root
        and outside the trash itself.
        """
        if not rel:
            return None
        root = os.path.realpath(self.root)
        trash = os.path.realpath(self.trash_root)
        abs_src = resolve_output_path(rel)
        if (
            abs_src is None
            or abs_src == root
            or abs_src == trash
            or abs_src.startswith(trash + os.sep)
        ):
            logger.error("prune_library: refusing to trash %r: outside the library", rel)
            return None
        if not os.path.isdir(abs_src):
            return None
        clean_rel = os.path.relpath(abs_src, root)
        dest = os.path.join(self.trash_root, clean_rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest):
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            dest = os.path.join(self.trash_root, f"{stamp}_{clean_rel}")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(abs_src, dest)
        return dest

    def _audit(self, entry):
        os.makedirs(self.trash_root, exist_ok=True)
        entry = {"ts": datetime.now().isoformat(), **entry}
        with open(os.path.join(self.trash_root, "audit.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
