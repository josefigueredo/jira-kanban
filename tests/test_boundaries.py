"""The read side of jtk never imports the write side, and the shared core imports neither (spec 2026-10-09, «Estructura»).

cli.py is the composition root: it wires both sides on purpose and is the only module allowed to."""
from __future__ import annotations

import ast
import unittest

from helpers import ROOT

PACKAGE = ROOT / "jkan"
CORE = {"jira", "config", "journal", "people", "guard", "state"}
READ = {"window", "queries", "standup", "stats", "render", "roles", "board_profile", "board_cli", "views", "team",
        "team_render", "team_cli"}
WRITE = {"sync", "spec", "description", "evidence", "kanban", "template", "preview", "plan", "applier", "plan_cli"}
COMPOSITION_ROOT = {"cli", "__init__"}


def imports_of(source: str) -> set:
    """The sibling modules a module imports with `from . import x` or `from .x import y`."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            if node.module is None:
                found |= {alias.name for alias in node.names}
            else:
                found.add(node.module.split(".")[0])
    return found


def existing(names: set) -> list:
    return sorted(n for n in names if (PACKAGE / f"{n}.py").is_file())


def imports_in(name: str) -> set:
    return imports_of((PACKAGE / f"{name}.py").read_text(encoding="utf-8"))


class BoundariesTest(unittest.TestCase):
    def test_imports_of_reads_both_import_forms(self):
        source = "from . import sync, queries\nfrom .jira import Jira\nimport json\n"
        self.assertEqual(imports_of(source), {"sync", "queries", "jira"})

    def test_every_module_belongs_to_a_side(self):
        on_disk = {p.stem for p in PACKAGE.glob("*.py")}
        self.assertEqual(sorted(on_disk - CORE - READ - WRITE - COMPOSITION_ROOT), [],
                         "a new module must be listed in CORE, READ or WRITE in tests/test_boundaries.py")

    def test_the_read_side_never_imports_the_write_side(self):
        for name in existing(READ):
            self.assertEqual(imports_in(name) & WRITE, set(), f"{name} imports the write side")

    def test_the_core_imports_neither_side(self):
        for name in existing(CORE):
            self.assertEqual(imports_in(name) & (READ | WRITE), set(), f"{name} imports a side")


if __name__ == "__main__":
    unittest.main()
