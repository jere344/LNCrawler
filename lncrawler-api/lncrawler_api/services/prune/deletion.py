"""Deleting a source row and moving its folder to the trash."""

import time

from django.db import transaction

from .common import _UnmappedComments, logger


class DeletionMixin:
    def _delete_source_named(self, source, reason, keeper=None, shift=0) -> bool:
        """Delete one source, porting its user data to ``keeper`` first.

        Returns True when the source is (or in a dry run would be) deleted. The
        row goes first, inside a transaction. The folder is moved to the trash
        only after the commit, so a failed delete never leaves a folder moved for
        a row that still exists. If the move itself fails the row is already
        gone and the folder stays where it is, for the opt-in unregistered sweep.
        """
        title = source.title
        source_name = source.external_source.source_name
        source_id = source.id
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
            rel = source.source_path
            dropped = 0
            try:
                with transaction.atomic():
                    if keeper is not None:
                        dropped = self._port_user_data(source, keeper, shift)
                    # Unlink the folder first: delete() would rmtree it otherwise.
                    source.source_path = None
                    source.save(update_fields=["source_path"])
                    source.delete()
            except _UnmappedComments as exc:
                self.stdout.write(
                    f"  KEEP source {source_id} {title!r}: {exc} (--force would drop them)"
                )
                return False
            except Exception as exc:
                logger.error("prune_library: failed deleting source %s: %s", source_id, exc)
                return False

            trash_path = None
            try:
                trash_path = self._move_to_trash(rel)
            except Exception as exc:
                logger.error(
                    "prune_library: deleted source %s but could not move %s to trash: %s",
                    source_id, rel, exc,
                )
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
            self.stdout.write(
                self.style.SUCCESS(f"  deleted source {source_id} {title!r} ({source_name}): {reason}")
            )
        self.deleted += 1
        self._maybe_sleep()
        return True

    def _maybe_sleep(self):
        if self.apply and self.sleep > 0:
            time.sleep(self.sleep)
