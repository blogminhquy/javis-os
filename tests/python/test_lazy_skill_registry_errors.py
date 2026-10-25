"""An unbound lazy skill lookup must let registry errors reach the caller.

AdaptiveContext reads an exception as "restore the legacy skill router". Swallowing a transient
`database is locked` into SkillSelection('none') would drop the whole skill index for that turn.
Only a bound task scope may answer 'none' on storage errors (it must not fall back to live disk).
"""
from _paths import ROOT, SERVER  # noqa: F401

import sqlite3
import tempfile
import unittest
from pathlib import Path

from lazy_skill_runtime import LazySkillSource


class _LockedRegistry:
    def refresh_skills(self, *args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    def revision(self, *args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    def search(self, *args, **kwargs):
        raise sqlite3.OperationalError("database is locked")


class LazyRegistryErrorTests(unittest.TestCase):
    def test_unbound_registry_error_propagates_for_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as brain:
            (Path(brain) / "skills" / "report").mkdir(parents=True)
            (Path(brain) / "skills" / "report" / "SKILL.md").write_text(
                "---\nname: report\ndescription: Monthly report\n---\nBody.\n", encoding="utf-8")
            with self.assertRaises(sqlite3.Error):
                LazySkillSource(_LockedRegistry()).resolve(brain, "use the report skill")


if __name__ == "__main__":
    unittest.main()
