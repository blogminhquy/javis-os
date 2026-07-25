import asyncio
import json
from pathlib import Path

from fastapi import FastAPI

from task_store import TaskStore
from tasks import TasksDeps, TasksFeature


def _atomic(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


async def _workflow(*_args, **_kwargs):
    if False:
        yield {}


async def _report(*_args, **_kwargs):
    return True


def _feature(tmp_path, brains):
    state = tmp_path / "state"
    app = FastAPI()

    def resolve(value):
        candidate = Path(str(value))
        if candidate.is_dir():
            return str(candidate)
        return str(brains[0])

    deps = TasksDeps(
        brain_root=resolve,
        atomic_write_text=_atomic,
        execute_workflow=_workflow,
        workflows_dir=lambda brain: Path(resolve(brain)) / "workflows",
        build_system_prompt=lambda brain: "system",
        aux_model=lambda: None,
        safe_tools=["Read", "Write"],
        state_dir=state,
        scheduler_brains=lambda: [str(p) for p in brains],
        report=_report,
    )
    return TasksFeature(deps)


def test_legacy_json_migrates_once_and_keeps_snapshot(tmp_path):
    brain = tmp_path / "Brain A"
    legacy = brain / "Javis" / "kanban.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps(
            {
                "orchestration": "auto",
                "tasks": [
                    {
                        "id": "t_old",
                        "title": "Legacy task",
                        "intent": "Keep this task",
                        "status": "ready",
                        "priority": 2,
                        "needs_approval": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    feature = _feature(tmp_path, [brain])
    root = feature._ensure(str(brain))
    assert feature.store.board_mode(root) == "auto"
    assert feature.store.get_task("t_old")["intent"] == "Keep this task"

    feature._snapshot(root)
    mirrored = json.loads(legacy.read_text(encoding="utf-8"))
    assert mirrored["schema"] == 2
    assert mirrored["source"] == "kanban.sqlite3"
    assert [t["id"] for t in mirrored["tasks"]] == ["t_old"]
    feature.store.close()


def test_claim_is_compare_and_set_and_targets_exact_task(tmp_path):
    store = TaskStore(tmp_path / "queue.sqlite3")
    root = str(tmp_path / "brain")
    Path(root).mkdir()
    first = store.enqueue(root, "First", "one", capability="files", status="ready")
    second = store.enqueue(root, "Second", "two", capability="files", status="ready")

    claimed = store.claim(second, "worker-2")
    assert claimed and claimed["id"] == second
    assert store.get_task(first)["status"] == "ready"
    assert store.claim(second, "worker-race") is None

    done = store.complete(second, "worker-2", "finished")
    assert done["status"] == "done"
    assert store.get_task(first)["status"] == "ready"
    assert len(store.list_runs(second)) == 1
    store.close()


def test_dependency_waits_and_promotes_after_parent_done(tmp_path):
    store = TaskStore(tmp_path / "queue.sqlite3")
    root = str(tmp_path / "brain")
    Path(root).mkdir()
    parent = store.enqueue(root, "Parent", "parent", capability="files", status="ready")
    child = store.enqueue(
        root, "Child", "child", deps=[parent], capability="files", status="todo"
    )
    assert store.promote_dependencies(root) == 0
    claimed = store.claim(parent, "worker-parent")
    assert claimed
    store.complete(parent, "worker-parent", "ok")
    assert store.promote_dependencies(root) == 1
    assert store.get_task(child)["status"] == "ready"
    store.close()


def test_recovers_only_codex_global_flag_blocks_once(tmp_path):
    store = TaskStore(tmp_path / "queue.sqlite3")
    root = str(tmp_path / "brain")
    Path(root).mkdir()
    affected = store.enqueue(
        root, "Affected", "run", capability="code", status="ready"
    )
    other = store.enqueue(
        root, "Needs input", "wait", capability="external-write", status="ready"
    )
    assert store.claim(affected, "worker-a")
    store.block(
        affected,
        "worker-a",
        "engine",
        "Codex lỗi (exit 2): error: unexpected argument '--ask-for-approval' found",
    )
    assert store.claim(other, "worker-b")
    store.block(other, "worker-b", "needs_input", "Cần người dùng chọn tài khoản")

    assert store.recover_codex_global_flag_blocks(root) == 1
    recovered = store.get_task(affected)
    assert recovered["status"] == "ready"
    assert recovered["attempts"] == 0
    assert recovered["block_reason"] == ""
    assert store.get_task(other)["status"] == "blocked"
    assert store.recover_codex_global_flag_blocks(root) == 0
    assert any(
        event["event_type"] == "system_recovered"
        for event in store.list_events(affected)
    )
    store.close()


def test_dispatcher_scans_all_brains_and_workers_finish_independently(tmp_path):
    async def scenario():
        brain_a = tmp_path / "Brain A"
        brain_b = tmp_path / "Brain B"
        brain_a.mkdir()
        brain_b.mkdir()
        feature = _feature(tmp_path, [brain_a, brain_b])

        async def execute(task):
            await asyncio.sleep(0.02)
            return f"done {task['title']}", "", False, {"provider": "test"}

        feature._execute = execute
        roots = [feature._ensure(str(brain_a)), feature._ensure(str(brain_b))]
        ids = []
        for index, root in enumerate(roots):
            feature.store.set_orchestration(root, "auto")
            ids.append(
                feature.store.enqueue(
                    root,
                    f"Task {index}",
                    "execute",
                    capability="files",
                    status="ready",
                )
            )
        feature.start()
        for _ in range(100):
            if all(feature.store.get_task(tid)["status"] == "done" for tid in ids):
                break
            await asyncio.sleep(0.02)
        assert [feature.store.get_task(tid)["status"] for tid in ids] == ["done", "done"]
        assert all(feature.store.list_runs(tid)[0]["status"] == "completed" for tid in ids)
        await feature.shutdown()

    asyncio.run(scenario())


def test_run_selected_task_does_not_pick_older_ready_task(tmp_path):
    async def scenario():
        brain = tmp_path / "Brain"
        brain.mkdir()
        feature = _feature(tmp_path, [brain])
        root = feature._ensure(str(brain))
        older = feature.store.enqueue(
            root, "Older", "older", priority=1, capability="files", status="ready"
        )
        selected = feature.store.enqueue(
            root, "Selected", "selected", priority=3, capability="files", status="ready"
        )

        async def execute(task):
            return task["id"], "", False, {}

        feature._execute = execute
        assert await feature._claim_and_spawn(selected)
        await feature._workers[selected]
        assert feature.store.get_task(selected)["status"] == "done"
        assert feature.store.get_task(older)["status"] == "ready"
        await feature.shutdown()

    asyncio.run(scenario())
