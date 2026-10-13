"""Where jtk keeps its data in a project: ./.jira-team-kit/ (epics, write log, create-in-flight files, conventions).

Until the jk -> jtk rename the folder was called .jira-kanban. A project that still has that one gets it moved to the new
name the first time any command asks where the data is, so nothing is lost and nothing has to be done by hand.
"""
from __future__ import annotations

from pathlib import Path

ROOT = ".jira-team-kit"
LEGACY_ROOT = ".jira-kanban"


def data_dir(project: Path) -> Path:
    """The data folder of `project`. Moves a legacy folder to the new name when only the legacy one exists.

    Both present: the new one wins and the legacy one is left alone (someone put data in both; merging is not ours to
    guess). A legacy name that is a file, or a move that fails (read-only, permissions), is not an error: the new path is
    returned in the first case and the legacy folder keeps being used in the second."""
    new, legacy = project / ROOT, project / LEGACY_ROOT
    if new.exists() or not legacy.is_dir():
        return new
    try:
        legacy.rename(new)
    except OSError:
        return legacy
    return new
