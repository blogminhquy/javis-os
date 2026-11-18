"""One list of every workflow gate waiting for the owner (the Quy trinh tab's pending-approval strip).

    python tests/python/test_kanban_approvals_view.py

Owner, 17/11/2026: approvals must show in one place, the Quy trinh tab, with the files to read, including a workflow
handed over through the Kanban that never showed there. `TasksFeature.approvals_view` lists them.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
from pathlib import Path

from tasks import TasksDeps, TasksFeature


def _atomic(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _feature(tmp_path):
    brain = tmp_path / "brain"
    brain.mkdir(parents=True, exist_ok=True)

    async def _workflow(*_a, **_k):
        yield {"type": "done", "result": ""}

    deps = TasksDeps(
        brain_root=lambda v: str(brain), atomic_write_text=_atomic, execute_workflow=_workflow,
        workflows_dir=lambda b: Path(brain) / "workflows", build_system_prompt=lambda b: "system",
        aux_model=lambda: None, safe_tools=["Read", "Write"], state_dir=tmp_path / "state",
        scheduler_brains=lambda: [str(brain)],
    )
    return TasksFeature(deps), str(brain)


def _gate(feature, brain, title, route, question):
    root = feature._ensure(brain)
    tid = feature.store.enqueue(root, title, "x", capability="files", status="ready", route=route)
    assert feature.store.claim(tid, "w")
    feature.store.ask(tid, "w", question, result="")
    return tid


def test_lists_only_workflow_gates_with_links(tmp_path):
    feature, brain = _feature(tmp_path)
    q = ("DUYỆT CONTENT. Đọc tại marketing/2026-11/sky/story-script.md và ảnh marketing/2026-11/sky/sky.png, "
         "video marketing/2026-11/sky/clip.mp4. Biên bản tong-duyet/content/r07.md")
    wf = _gate(feature, brain, "SKY tập 0", "wf:san-xuat-clip-sky", q)
    _gate(feature, brain, "Việc thường", "auto", "Bạn muốn gì?")
    out = feature.approvals_view(brain)
    assert out["ok"] and [i["id"] for i in out["items"]] == [wf]
    item = out["items"][0]
    assert item["workflow"] == "san-xuat-clip-sky" and item["can_answer"] is True
    kinds = {l["path"]: l["kind"] for l in item["links"]}
    assert kinds["marketing/2026-11/sky/story-script.md"] == "doc"
    assert kinds["marketing/2026-11/sky/sky.png"] == "image"
    assert kinds["marketing/2026-11/sky/clip.mp4"] == "video"
    assert kinds["tong-duyet/content/r07.md"] == "doc"


def test_answered_gate_leaves_the_list(tmp_path):
    feature, brain = _feature(tmp_path)
    tid = _gate(feature, brain, "SKY", "wf:x", "Duyệt?")
    assert len(feature.approvals_view(brain)["items"]) == 1
    done, err = feature.store.answer(tid, "Duyệt")
    assert done and not err
    assert feature.approvals_view(brain)["items"] == []


def test_links_ignore_parent_paths_and_dedupe():
    links = TasksFeature.approval_links("a/b.md a/b.md ../x/secret.md https://e.com/a/b.png")
    assert [l["path"] for l in links] == ["a/b.md"]


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
