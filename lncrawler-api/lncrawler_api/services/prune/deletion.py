"""Deleting a source row and moving its folder to the trash."""

import time
from functools import partial

from lncrawler_api.models.sources_models import refresh_novel_adult
from lncrawler_api.services.folder_guard import FolderBusy, locked_move
from lncrawler_api.services.novel_deletion import after_source_deleted
from lncrawler_api.services.novel_operations import file_journal

from .common import _UnmappedComments, logger


class DeletionMixin:
    def _delete_source_named(self, source, reason, keeper=None, shift=0) -> bool:
        """Delete one source, porting its user data to ``keeper`` first.

        Returns True when the source is (or in a dry run would be) deleted. The
        row and the folder move to the trash happen in one locked transaction: a
        failure of either undoes both, so a folder is never moved for a row that
        still exists. A novel with an active crawl is skipped (FolderBusy).
        """
        title = source.title
        source_name = source.external_source.source_name
        source_id = source.id
        novel_id = source.novel_id
        port = " and port user data" if keeper is not None else ""
        if not self.apply:
            if keeper is not None:
                unmapped = len(self._unmapped_comments(source, keeper, shift))
                if unmapped and not self.force:
                    self.stdout.write(
                        f"  [DRY-RUN] would KEEP source {source_id} {title!r}: "
                        f"{unmapped} comment(s) cannot be mapped (--force would drop them)"
                    )
                    return False
                if unmapped:
                    port += f" (would drop {unmapped} unmapped comment(s))"
            self.stdout.write(
                f"  [DRY-RUN] would delete source {source_id} {title!r} "
                f"({source_name}){port}: {reason}"
            )
        else:
            dropped = 0
            trash_path = None
            novel_deletion = None
            try:
                with file_journal() as files:
                    with locked_move(source.novel):
                        # Under the lock: the folder name may have changed since the scan.
                        source.novel.refresh_from_db(fields=["novel_path"])
                        rel = source.source_path
                        if keeper is not None:
                            dropped = self._port_user_data(source, keeper, shift)
                        # Unlink the folder first: delete() would rmtree it otherwise.
                        source.source_folder = None
                        source.save(update_fields=["source_folder"])
                        source.delete(files=files)
                        refresh_novel_adult([novel_id])
                        trash_path = self._move_to_trash(rel, files) if rel else None
                        # Last source of its novel: the novel goes too, its folder to the trash.
                        novel_deletion = after_source_deleted(
                            novel_id, trash=partial(self._move_to_trash, files=files), files=files,
                        )
            except FolderBusy:
                self.stdout.write(
                    f"  busy, source {source_id} {title!r} kept for a later run"
                )
                return False
            except _UnmappedComments as exc:
                self.stdout.write(
                    f"  KEEP source {source_id} {title!r}: {exc} (--force would drop them)"
                )
                return False
            except Exception as exc:
                logger.error("prune_library: failed deleting source %s: %s", source_id, exc)
                return False

            self._audit({
                "kind": "source",
                "id": source_id,
                "title": title,
                "source_name": source_name,
                "reason": reason,
                "keeper_id": keeper.id if keeper else None,
                "dropped_comments": dropped,
                "trash_path": trash_path,
            })
            if novel_deletion is not None:
                self._audit({
                    "kind": "novel",
                    "id": novel_id,
                    "reason": "last source deleted",
                    "trash_path": novel_deletion.trash_path,
                })
            self.stdout.write(
                self.style.SUCCESS(f"  deleted source {source_id} {title!r} ({source_name}): {reason}")
            )
        self.deleted += 1
        self._maybe_sleep()
        return True

    def _maybe_sleep(self):
        if self.apply and self.sleep > 0:
            time.sleep(self.sleep)
