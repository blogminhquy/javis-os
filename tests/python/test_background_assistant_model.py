"""Reminders and loops made in an assistant's chat run on that assistant's own model and effort.

    python tests/run.py background_assistant_model        (no network, no model call)

Ported from PR #1847 by tunganh0990. Since 25/11/2026 a Kanban job given to an assistant runs on the assistant's model at
its level (`main._agent_job_spec` + `main._aux_swap_spec`). A reminder or a loop made in that assistant's chat already ran
AS the assistant (its prompt, memory, rules) but still on the background model. Now it takes the same path; the loop's
independent verification run stays on the background model, and an assistant that is gone or left on "Default" with no
level of its own keeps the background model, as before.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-bg-assistant-"))

import pytest  # noqa: E402

import reminders  # noqa: E402
import self_improve  # noqa: E402

MINH = {"provider": "openai-oauth", "model": "gpt-5.5", "reasoning": "low"}


class FakeCli:
    max_wall_s = 0
    model = None

    def __init__(self, system_prompt="", **kw):
        self.system_prompt = system_prompt
        self.via = None

    def is_available(self):
        return True

    async def query(self, prompt):
        if "KIỂM CHỨNG" in (self.system_prompt or ""):
            yield {"type": "final", "content": '{"pass": true, "reason": "ok"}'}
            return
        yield {"type": "final", "content": "Đã đăng 1 video."}


def _atomic(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def _agent_prompt(brain, slug):
    if slug not in ("minh", "lan"):
        raise FileNotFoundError(slug)
    return f"SYS-AGENT {slug}"


class Recorder:
    """The two background routers: `aux_swap` (background model) and `aux_swap_spec` (an explicit first link)."""

    def __init__(self):
        self.plain, self.spec, self.asked = [], [], []

    def agent_job_spec(self, brain, slug):
        self.asked.append(slug)
        return dict(MINH) if slug == "minh" else None      # lan: "Default" model, no level of its own

    def aux_swap(self, cli, mode=None, tag=None):
        self.plain.append((mode, tag))
        cli.via = "background"
        return cli

    def aux_swap_spec(self, cli, mode, tag, spec):
        self.spec.append((mode, tag, spec))
        cli.via = "assistant"
        return cli


@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setattr(reminders, "claude_engine", FakeCli)
    monkeypatch.setattr(self_improve, "claude_engine", FakeCli)


# ---------------------------------------------------------------- reminders

def _reminders(tmp_path, rec, wired=True):
    async def send(chat_id, text, **kw):
        return True, ""

    extra = {"agent_job_spec": rec.agent_job_spec, "aux_swap_spec": rec.aux_swap_spec} if wired else {}
    return reminders.RemindersFeature(reminders.RemindersDeps(
        brain_root=lambda _b: str(tmp_path), atomic_write_text=_atomic, send_telegram=send,
        build_system_prompt=lambda _b: "SYS-JAVIS", aux_model=lambda: None, safe_tools=[], readonly_tools=[],
        scheduler_brains=lambda: [str(tmp_path)], build_agent_prompt=_agent_prompt,
        finish_agent_run=lambda b, s, t, o: o, aux_swap=rec.aux_swap, **extra))


@pytest.mark.parametrize("level", ["suggest", "auto", "full"])
def test_reminder_runs_on_the_assistants_model_and_effort(tmp_path, fake_engine, level):
    rec = Recorder()
    feature = _reminders(tmp_path, rec)
    out, err = asyncio.run(feature._run_task(str(tmp_path), "Đăng video.", level, agent="minh"))
    assert out and not err
    assert rec.spec == [(level, "reminder", MINH)], rec.spec
    assert rec.plain == [], "the background model is not used for the assistant's own run"


def test_reminder_without_an_own_model_keeps_the_background_model(tmp_path, fake_engine):
    rec = Recorder()
    feature = _reminders(tmp_path, rec)
    asyncio.run(feature._run_task(str(tmp_path), "Đăng video.", "full", agent="lan"))       # "Default" model
    asyncio.run(feature._run_task(str(tmp_path), "Đăng video.", "full", agent="gone"))      # assistant deleted
    asyncio.run(feature._run_task(str(tmp_path), "Nhắc gọi khách.", "full"))                # plain reminder
    assert rec.spec == []
    assert rec.plain == [("full", "reminder")] * 3
    assert rec.asked == ["lan"], "a deleted assistant or a plain reminder never asks for a model"


def test_reminder_deps_without_the_helpers_keep_the_old_path(tmp_path, fake_engine):
    rec = Recorder()
    feature = _reminders(tmp_path, rec, wired=False)
    asyncio.run(feature._run_task(str(tmp_path), "Đăng video.", "full", agent="minh"))
    assert rec.plain == [("full", "reminder")] and rec.spec == []


# ---------------------------------------------------------------- loops

def _loop_feature(tmp_path, rec):
    return self_improve.LoopFeature(self_improve.LoopDeps(
        build_system_prompt=lambda b: "SYS-JAVIS", brain_root=lambda b: str(tmp_path), aux_model=lambda: None,
        atomic_write_text=_atomic, project_root=Path("."), state_dir=tmp_path / "state",
        safe_tools=["Read", "Write"], readonly_tools=["Read"], build_agent_prompt=_agent_prompt,
        finish_agent_run=lambda b, s, t, o: o, aux_swap=rec.aux_swap,
        agent_job_spec=rec.agent_job_spec, aux_swap_spec=rec.aux_swap_spec))


def _loop_file(tmp_path, slug, mode, agent):
    d = tmp_path / "Javis" / "loops"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.md").write_text(
        f"---\nname: Video\ngoal: custom\nmode: {mode}\nenabled: false\n"
        + (f"agent: {agent}\n" if agent else "") + "---\nĐăng một video.\n", encoding="utf-8")


@pytest.mark.parametrize("mode", ["auto", "full"])
def test_loop_round_runs_on_the_assistants_model_and_verification_stays_on_background(tmp_path, fake_engine, mode):
    rec = Recorder()
    lf = _loop_feature(tmp_path, rec)
    _loop_file(tmp_path, "video", mode, "minh")
    r = asyncio.run(lf.run_cycle("brain", "video", "manual"))
    assert r.get("ok"), r
    assert rec.spec == [(mode, "loop", MINH)], rec.spec
    assert rec.plain == [("suggest", "loop")], "the verification run is on the background model, read-only"


def test_loop_without_an_assistant_keeps_the_background_model(tmp_path, fake_engine):
    rec = Recorder()
    lf = _loop_feature(tmp_path, rec)
    _loop_file(tmp_path, "plain", "suggest", "")
    _loop_file(tmp_path, "lan", "suggest", "lan")
    asyncio.run(lf.run_cycle("brain", "plain", "manual"))
    asyncio.run(lf.run_cycle("brain", "lan", "manual"))
    assert rec.spec == [] and rec.plain == [("suggest", "loop")] * 2


# ---------------------------------------------------------------- main.py wiring

def test_main_wires_reminders_and_loops_to_the_assistant_helpers(monkeypatch):
    import main

    asked = []
    monkeypatch.setattr(main, "_agent_job_spec", lambda root, slug, agent_key=None, tag="kanban":
                        asked.append((root, slug, agent_key, tag)) or dict(MINH))
    assert main.reminders_feature.deps.agent_job_spec("b", "minh") == MINH
    assert main.loop_feature.deps.agent_job_spec("b", "minh") == MINH
    assert asked == [("b", "minh", None, "reminder"), ("b", "minh", None, "loop")]
    assert main.reminders_feature.deps.aux_swap_spec is main._aux_swap_spec
    assert main.loop_feature.deps.aux_swap_spec is main._aux_swap_spec
    assert main.tasks_feature.deps.aux_swap_spec is main._aux_swap_spec


def test_default_model_assistant_reads_the_background_model_of_its_own_job(monkeypatch, tmp_path):
    import main

    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "lan.md").write_text("---\nname: Lan\nrole: r\nreasoning: high\n---\nBạn là Lan.\n",
                                                encoding="utf-8")
    tags = []
    monkeypatch.setattr(main, "_agent_persona", lambda root, slug, key=None: "persona")
    monkeypatch.setattr(main, "_agent_md_path", lambda root, slug: tmp_path / "agents" / f"{slug}.md")
    monkeypatch.setattr(main.aux_engine, "read_spec",
                        lambda settings=None, tag=None: tags.append(tag) or {"provider": "anthropic-cli", "model": ""})
    assert main._agent_job_spec(str(tmp_path), "lan", tag="reminder")["reasoning"] == "high"
    assert main._agent_job_spec(str(tmp_path), "lan")["reasoning"] == "high"
    assert tags == ["reminder", "kanban"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
