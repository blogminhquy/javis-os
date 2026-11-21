"""Regression tests for model routing and fallback execution evidence."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

_TEST_DIR = Path(__file__).resolve().parent
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))
from _paths import ROOT, SERVER  # noqa: E402,F401

_TMP = Path(tempfile.mkdtemp(prefix="javis_model_evidence_test_"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["BRAINS_DIR"] = str(_TMP / "brains")

import pytest  # noqa: E402
import aux_engine  # noqa: E402
from tasks import TasksDeps, TasksFeature  # noqa: E402


class _FakeEngine:
    def __init__(self, provider: str, model: str, *, available: bool = True, events=None, tag: str = ""):
        self.provider, self.model, self._available = provider, model, available
        self._events = list(events or [{"type": "final", "content": "done"}])
        self.tag, self.calls = tag, 0

    def is_available(self) -> bool:
        return self._available

    def reset_session(self):
        return None

    async def query(self, _prompt: str):
        self.calls += 1
        for ev in self._events:
            yield ev


def _make_feature(tmp_path: Path) -> tuple[Path, TasksFeature]:
    brain = tmp_path / "BrainModel"
    brain.mkdir(exist_ok=True)

    def _atomic_mk(p, t):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text(t, encoding="utf-8")

    deps = TasksDeps(
        brain_root=lambda _v: str(brain), atomic_write_text=_atomic_mk,
        execute_workflow=lambda *_a, **_k: iter(()), workflows_dir=lambda b: Path(b) / "workflows",
        build_system_prompt=lambda _b: "sys", aux_model=lambda: None,
        safe_tools=[], state_dir=tmp_path / "state",
    )
    return brain, TasksFeature(deps)


def test_fallback_chain_records_primary_and_fallback_evidence():
    """_FallbackChain and execution_info record actual provider/model and fallback reason."""
    async def _collect(chain):
        return [ev async for ev in chain.query("hello")]

    cfg = {"provider": "anthropic-cli", "model": "claude-sonnet-4-6"}
    aux_engine._COOLDOWN.clear()
    try:
        # Case 1: healthy primary engine runs cleanly with no fallback.
        p1, s1 = _FakeEngine("anthropic-cli", "claude-sonnet-4-6"), _FakeEngine("openrouter", "openai/gpt-4o-mini")
        c1 = aux_engine._FallbackChain([p1, s1])
        assert any(ev.get("type") == "final" for ev in asyncio.run(_collect(c1))) and p1.calls == 1 and s1.calls == 0
        assert aux_engine.execution_info(c1, configured=cfg) == {"provider": "anthropic-cli", "model": "claude-sonnet-4-6"}

        # Case 2: primary fails before tool_call -> secondary runs and records fallback evidence.
        aux_engine._COOLDOWN.clear()
        p2 = _FakeEngine("anthropic-cli", "claude-sonnet-4-6", events=[{"type": "error", "content": "rate limit 429"}])
        s2 = _FakeEngine("openai", "gpt-5-mini")
        c2 = aux_engine._FallbackChain([p2, s2])
        assert any(ev.get("type") == "final" for ev in asyncio.run(_collect(c2))) and p2.calls == 1 and s2.calls == 1
        info2 = aux_engine.execution_info(c2, configured=cfg)
        assert (info2["provider"], info2["model"], info2["fallback_from"]) == ("openai", "gpt-5-mini", "anthropic-cli")
        assert "429" in info2["fallback_reason"]

        # Case 3: primary in cooldown -> secondary runs directly with cooldown reason.
        pc, sc = _FakeEngine("anthropic-cli", "claude-sonnet-4-6"), _FakeEngine("openai", "gpt-5-mini")
        cc = aux_engine._FallbackChain([pc, sc])
        assert any(ev.get("type") == "final" for ev in asyncio.run(_collect(cc))) and pc.calls == 0 and sc.calls == 1
        infoc = aux_engine.execution_info(cc, configured=cfg)
        assert (infoc["provider"], infoc["fallback_from"]) == ("openai", "anthropic-cli")
        assert "cooldown" in infoc["fallback_reason"].lower()

        # Case 4: primary in cooldown, secondary fails, primary recovers -> NO self-fallback.
        prec = _FakeEngine("anthropic-cli", "claude-sonnet-4-6")
        sfail = _FakeEngine("openai", "gpt-5-mini", events=[{"type": "error", "content": "rate limit 429"}])
        crec = aux_engine._FallbackChain([prec, sfail])
        assert any(ev.get("type") == "final" for ev in asyncio.run(_collect(crec))) and prec.calls == 1 and sfail.calls == 1
        assert aux_engine.execution_info(crec, configured=cfg) == {"provider": "anthropic-cli", "model": "claude-sonnet-4-6"}

        # Case 5: primary fails AFTER tool_call -> chain stops without running secondary.
        aux_engine._COOLDOWN.clear()
        p5 = _FakeEngine("anthropic-cli", "claude-sonnet-4-6",
                         events=[{"type": "tool_call", "name": "send"}, {"type": "error", "content": "network reset"}])
        s5 = _FakeEngine("openai", "gpt-5-mini")
        c5 = aux_engine._FallbackChain([p5, s5])
        assert asyncio.run(_collect(c5))[-1]["type"] == "error" and p5.calls == 1 and s5.calls == 0
        assert "network reset" in c5.last_run().get("error", "")

        # Case 6: primary unavailable -> secondary runs; single-engine mismatch also records fallback_from.
        aux_engine._COOLDOWN.clear()
        p6, s6 = _FakeEngine("anthropic-cli", "claude-sonnet-4-6", available=False), _FakeEngine("gemini", "gemini-2.5-flash")
        c6 = aux_engine._FallbackChain([p6, s6])
        assert any(ev.get("type") == "final" for ev in asyncio.run(_collect(c6)))
        info6 = aux_engine.execution_info(c6, configured=cfg)
        assert (info6["provider"], info6["model"], info6["fallback_from"]) == ("gemini", "gemini-2.5-flash", "anthropic-cli")
        assert info6["fallback_reason"]
        single = aux_engine.execution_info(_FakeEngine("openrouter", "openai/gpt-4o-mini"), configured=cfg)
        assert (single["provider"], single["fallback_from"]) == ("openrouter", "anthropic-cli") and single["fallback_reason"]

        # Case 7: primary unavailable and secondary runs and yields error (terminal all-fail & acted early return).
        aux_engine._COOLDOWN.clear()
        p7 = _FakeEngine("anthropic-cli", "claude-sonnet-4-6", available=False)
        s7 = _FakeEngine("openai", "gpt-5-mini", events=[{"type": "error", "content": "bad gateway 502"}])
        c7 = aux_engine._FallbackChain([p7, s7])
        assert asyncio.run(_collect(c7))[-1]["type"] == "error" and p7.calls == 0 and s7.calls == 1
        info7 = aux_engine.execution_info(c7, configured=cfg)
        assert (info7["provider"], info7["model"], info7["fallback_from"]) == ("openai", "gpt-5-mini", "anthropic-cli")
        assert info7["fallback_reason"] and "502" in c7.last_run().get("error", "")

        aux_engine._COOLDOWN.clear()
        p8 = _FakeEngine("anthropic-cli", "claude-sonnet-4-6", available=False)
        s8 = _FakeEngine("gemini", "gemini-2.5-flash",
                         events=[{"type": "tool_call", "name": "read"}, {"type": "error", "content": "tool timeout"}])
        c8 = aux_engine._FallbackChain([p8, s8])
        assert asyncio.run(_collect(c8))[-1]["type"] == "error" and p8.calls == 0 and s8.calls == 1
        info8 = aux_engine.execution_info(c8, configured=cfg)
        assert (info8["provider"], info8["model"], info8["fallback_from"]) == ("gemini", "gemini-2.5-flash", "anthropic-cli")
        assert info8["fallback_reason"] and "tool timeout" in c8.last_run().get("error", "")
    finally:
        aux_engine._COOLDOWN.clear()


def test_kanban_execute_and_card_surface_model_fallback_metadata(tmp_path: Path):
    """Kanban _execute and _card must surface provider, model, fallback_from, and fallback_reason."""
    aux_engine._COOLDOWN.clear()
    brain, feat = _make_feature(tmp_path)
    try:
        tid = feat.store.enqueue(str(brain), "Model audit", "Run check", capability="files", status="ready")
        task = feat.store.get_task(tid)
        primary = _FakeEngine("anthropic-cli", "claude-sonnet-4-6",
                              events=[{"type": "error", "content": "plan quota exhausted"}])
        fallback = _FakeEngine("openrouter", "openai/gpt-4o-mini",
                               events=[{"type": "final", "content": "Verified result"}])
        chain = aux_engine._FallbackChain([primary, fallback])

        with patch.object(aux_engine, "read_spec", return_value={"provider": "anthropic-cli", "model": "claude-sonnet-4-6"}), \
                patch.object(aux_engine, "apply", return_value=chain), \
                patch("tasks.claude_engine", side_effect=lambda **kw: _FakeEngine("anthropic-cli", "claude-sonnet-4-6", tag=kw.get("tag", ""))):
            res, err, _ask, meta = asyncio.run(feat._execute(task))

        assert not err and "Verified result" in res
        assert (meta["provider"], meta["model"], meta["fallback_from"]) == ("openrouter", "openai/gpt-4o-mini", "anthropic-cli")
        assert "quota" in meta["fallback_reason"].lower()
        card = TasksFeature._card({**task, "metadata": meta})
        for key in ("provider", "model", "fallback_from", "fallback_reason"):
            assert key in card["metadata"], key
    finally:
        aux_engine._COOLDOWN.clear()
        feat.store.close()


def test_run_worker_preserves_run_metadata_and_clears_stale_fallback_on_retry(tmp_path: Path):
    """_run_worker records provider/model on error and needs_input and clears stale fallback on clean retry."""
    brain, feat = _make_feature(tmp_path)
    try:
        tid = feat.store.enqueue(
            str(brain), "Retry model audit", "Run check", capability="files", status="ready",
            metadata={"provider": "openrouter", "model": "openai/gpt-4o-mini",
                      "fallback_from": "anthropic-cli", "fallback_reason": "rate limit 429"},
        )

        async def _step(wid: str, res: str = "", err: str = "", ask: bool = False, **meta_extra) -> dict:
            async def _exec(_task):
                return (res, err, ask, {
                    "route": "auto", "capability": "files", "execution_mode": "auto",
                    "tool_calls": ["Read"], **meta_extra,
                })
            feat._execute = _exec
            await feat._run_worker(feat.store.claim(tid, wid), wid)
            return feat.store.get_task(tid)

        async def _run_sequence():
            # 1) Transient error on primary clears stale fallback_from/fallback_reason.
            t_err = await _step("w1", err="connection reset", provider="anthropic-cli", model="claude-sonnet-4-6")
            assert t_err["status"] == "ready"
            assert (t_err["metadata"]["provider"], t_err["metadata"]["model"]) == ("anthropic-cli", "claude-sonnet-4-6")
            assert "fallback_from" not in t_err["metadata"] and "fallback_reason" not in t_err["metadata"]

            # 2) needs_input after fallback records current provider/model/fallback and qa.
            t_ask = await _step("w2", res="[[NEEDS_INPUT]] Target branch?", ask=True, provider="openai",
                                model="gpt-5-mini", fallback_from="anthropic-cli", fallback_reason="rate limit 429")
            assert t_ask["status"] == "blocked" and t_ask["block_kind"] == "needs_input"
            assert (t_ask["metadata"]["provider"], t_ask["metadata"]["model"], t_ask["metadata"]["fallback_from"]) == (
                "openai", "gpt-5-mini", "anthropic-cli")

            # 3) Clean needs_input retry on primary clears stale fallback_from/fallback_reason.
            feat.store.answer(tid, "main")
            t_ask2 = await _step("w3", res="[[NEEDS_INPUT]] Confirm deploy?", ask=True,
                                 provider="anthropic-cli", model="claude-sonnet-4-6")
            assert (t_ask2["metadata"]["provider"], t_ask2["metadata"]["model"]) == ("anthropic-cli", "claude-sonnet-4-6")
            assert "fallback_from" not in t_ask2["metadata"] and "fallback_reason" not in t_ask2["metadata"]

            # 4) Clean completion retry on primary preserves qa and keeps fallback keys absent.
            feat.store.answer(tid, "yes")
            t_done = await _step("w4", res="Verified clean primary run", provider="anthropic-cli", model="claude-sonnet-4-6")
            assert t_done["status"] == "done" and t_done["metadata"].get("qa")
            assert (t_done["metadata"]["provider"], t_done["metadata"]["model"]) == ("anthropic-cli", "claude-sonnet-4-6")
            assert "fallback_from" not in t_done["metadata"] and "fallback_reason" not in t_done["metadata"]
            card = TasksFeature._card(t_done)
            assert (card["metadata"]["provider"], card["metadata"]["model"]) == ("anthropic-cli", "claude-sonnet-4-6")
            assert "fallback_from" not in card["metadata"] and "fallback_reason" not in card["metadata"]

        asyncio.run(_run_sequence())
    finally:
        feat.store.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
