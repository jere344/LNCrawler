"""Creating folders inside a novel or source folder without recreating a missing parent.

Folder guard, rule 1: a process holding an outdated path must fail loudly. So a
folder is created one level at a time with ``os.mkdir``, and the folder it sits in
must already exist. A missing base raises ``FileNotFoundError``.
"""

import os


def make_subfolders(base, *names):
    """Create ``base/names[0]/names[1]/...`` one level at a time; existing levels are kept.

    ``base`` itself is never created. Only the folder that does not exist yet is made,
    and only when its parent exists, so a stale base raises ``FileNotFoundError``.
    """
    path = os.fspath(base)
    for name in names:
        path = os.path.join(path, name)
        try:
            os.mkdir(path)
        except FileExistsError:
            pass
