"""Self-learning never rewrites an existing memory fact (#1800).

A fork returned a fact whose `supersedes` was its own slug. The append-only guard only skipped an
existing file when `supersedes` was empty, so the file (30 lines of deploy history and lessons) was
replaced by a one-paragraph summary and its `created` date reset to today.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
from pathlib import Path

from learn import LearnDeps, LearnFeature


def _write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def _feature(tmp_path):
    deps = LearnDeps(
        build_system_prompt=lambda b: "",
        brain_root=lambda b: str(tmp_path),
        brain_memory_dir=lambda b: tmp_path / "memory",
        resolve_subfolder=lambda a, b, c: str(tmp_path / "Wiki"),
        aux_model=lambda: None,
        atomic_write_text=_write,
        sessions_store=None,
        state_dir=tmp_path,
        readonly_tools=["Read"],
    )
    return LearnFeature(deps)


CAPS = {"memory": True, "wiki": False, "skill": False, "task": False,
        "agent": False, "workflow": False}

OLD = ("---\ntype: business\ncreated: 2026-10-01\nupdated: 2026-11-20\n---\n"
       "Odoo module cong trinh.\n\n## Lich su\n- v1 deploy\n- v2 deploy\n- bai hoc: backup truoc\n")


def _fact(**over):
    x = {"slug": "odoo-module", "title": "Odoo module", "body": "Short summary only.",
         "kind": "business", "confidence": 3, "supersedes": ""}
    x.update(over)
    return x


def _run(feature, facts):
    return feature._promote_sync("brain", {"facts": facts}, feature.read_config(), CAPS, allow_write=True)


def test_self_supersede_keeps_file(tmp_path):
    feature = _feature(tmp_path)
    fp = tmp_path / "memory" / "facts" / "odoo-module.md"
    _write(fp, OLD)
    rep = _run(feature, [_fact(supersedes="odoo-module")])
    assert fp.read_text(encoding="utf-8") == OLD, "a fact that supersedes itself must not overwrite the file"
    assert "odoo-module" not in rep["facts"]
    assert any("supersedes itself" in b for b in rep["blocked"]), rep["blocked"]


def test_existing_new_slug_with_other_supersedes_is_kept(tmp_path):
    feature = _feature(tmp_path)
    facts = tmp_path / "memory" / "facts"
    _write(facts / "odoo-module.md", OLD)
    _write(facts / "old-thing.md", "---\ntype: business\n---\nOld.\n")
    _run(feature, [_fact(supersedes="old-thing")])
    assert (facts / "odoo-module.md").read_text(encoding="utf-8") == OLD


def test_new_slug_superseding_old_still_works(tmp_path):
    feature = _feature(tmp_path)
    facts = tmp_path / "memory" / "facts"
    _write(facts / "odoo-module.md", OLD)
    rep = _run(feature, [_fact(slug="odoo-module-v3", body="New fact — replaces the old one.",
                               supersedes="odoo-module")])
    assert "odoo-module-v3" in rep["facts"], rep
    new_text = (facts / "odoo-module-v3.md").read_text(encoding="utf-8")
    assert "—" not in new_text and "–" not in new_text, new_text
    old_text = (facts / "odoo-module.md").read_text(encoding="utf-8")
    assert "superseded_by: odoo-module-v3" in old_text
    assert "- v2 deploy" in old_text, "the old file keeps its history"


if __name__ == "__main__":
    import tempfile
    for fn in (test_self_supersede_keeps_file, test_existing_new_slug_with_other_supersedes_is_kept,
               test_new_slug_superseding_old_still_works):
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
    print("ok")
