"""An agent doing a workflow step asks a colleague agent mid-task (javis_ask_agent).

    python tests/run.py agent_delegation      (no network)

Pins the guards that make delegation safe to leave running unattended: only colleagues listed in
`can_ask`, identity by ticket (not by an argument), one level deep, at most MAX_ASKS per step,
and the colleague runs through the caller's engine factory (same allowlist, same level).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import re

import agent_delegation as ad


def _run(coro):
    return asyncio.run(coro)


def _ticket(block):
    return re.search(r"ask_ticket=(ak_\S+)", block).group(1)


def setup_function(_fn):
    ad.reset_for_tests()


# ------------------------------------------------------------------ unit: guards

def test_no_targets_no_ticket():
    assert ad.issue("a", "A", {}, None) == ""
    # asking yourself is not a colleague
    assert ad.issue("a", "A", {"a": "A"}, None) == ""


def test_declared_targets_accepts_list_and_string():
    assert ad.declared_targets({"can_ask": ["x", "y", "x", ""]}) == ["x", "y"]
    assert ad.declared_targets({"can_ask": "x, y"}) == ["x", "y"]
    assert ad.declared_targets({}) == []


def test_ask_runs_listed_colleague_and_returns_answer():
    seen = []

    async def run(target, prompt):
        seen.append((target, prompt))
        return "ĐÃ SOÁT: khớp", ""

    block = ad.issue("sales", "Bảo Ngọc", {"acct": "Minh Châu"}, run)
    assert ad.ticket_in(block) and "`acct`: Minh Châu" in block
    out = _run(ad.ask(_ticket(block), "acct", "Soát giá 3 phòng"))
    assert out.startswith("Kết quả từ Minh Châu") and "ĐÃ SOÁT" in out
    assert seen[0][0] == "acct" and "Bảo Ngọc nhờ" in seen[0][1] and "Soát giá 3 phòng" in seen[0][1]


def test_unlisted_colleague_refused_without_running():
    ran = []

    async def run(target, prompt):
        ran.append(target)
        return "x", ""

    t = _ticket(ad.issue("sales", "S", {"acct": "A"}, run))
    out = _run(ad.ask(t, "hr", "việc"))
    assert out.startswith("ERROR") and "acct" in out and not ran


def test_forged_or_missing_ticket_refused():
    assert _run(ad.ask("ak_" + "x" * 20, "acct", "t")).startswith("ERROR")
    assert _run(ad.ask("", "acct", "t")).startswith("ERROR")


def test_ticket_accepted_with_or_without_prefix():
    async def run(target, prompt):
        return "ok", ""

    t = _ticket(ad.issue("s", "S", {"acct": "A"}, run))
    assert "ok" in _run(ad.ask(f"ask_ticket={t}", "acct", "t"))
    assert "ok" in _run(ad.ask(t, "acct", "t"))


def test_cap_of_asks_per_ticket():
    async def run(target, prompt):
        return "ok", ""

    t = _ticket(ad.issue("s", "S", {"acct": "A"}, run))
    outs = [_run(ad.ask(t, "acct", f"t{i}")) for i in range(ad.MAX_ASKS + 1)]
    assert all(o.startswith("Kết quả") for o in outs[:-1])
    assert outs[-1].startswith("ERROR") and str(ad.MAX_ASKS) in outs[-1]


def test_empty_task_refused():
    t = _ticket(ad.issue("s", "S", {"acct": "A"}, None))
    assert _run(ad.ask(t, "acct", "  ")).startswith("ERROR")


def test_colleague_error_and_exception_surface_as_error():
    async def fails(target, prompt):
        return "", "engine chết"

    async def boom(target, prompt):
        raise RuntimeError("nổ")

    t1 = _ticket(ad.issue("s", "S", {"acct": "A"}, fails))
    assert "engine chết" in _run(ad.ask(t1, "acct", "t"))
    t2 = _ticket(ad.issue("s", "S", {"acct": "A"}, boom))
    out = _run(ad.ask(t2, "acct", "t"))
    assert out.startswith("ERROR") and "nổ" in out


def test_timeout(monkeypatch):
    monkeypatch.setattr(ad, "ASK_TIMEOUT_S", 0.05)

    async def slow(target, prompt):
        await asyncio.sleep(1)
        return "late", ""

    t = _ticket(ad.issue("s", "S", {"acct": "A"}, slow))
    assert _run(ad.ask(t, "acct", "t")).startswith("ERROR")


def test_expired_ticket_refused(monkeypatch):
    async def run(target, prompt):
        return "ok", ""

    t = _ticket(ad.issue("s", "S", {"acct": "A"}, run))
    real = ad.time.time
    monkeypatch.setattr(ad.time, "time", lambda: real() + ad.TICKET_TTL_S + 1)
    assert _run(ad.ask(t, "acct", "t")).startswith("ERROR")


def test_plugin_registers_readonly_tool():
    import plugins_host
    path = ROOT / "system" / "plugins" / "javis-workflow" / "plugin.py"
    spec = importlib.util.spec_from_file_location("javis_workflow_plugin_ask", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    ctx = plugins_host.PluginContext("javis-workflow", "bundled", path.parent, None)
    m.register(ctx)
    tool = [t for t in ctx._tools if t["name"] == ad.TOOL_NAME][0]
    assert tool["min_mode"] == "readonly"

    async def run(target, prompt):
        return "từ plugin", ""

    t = _ticket(ad.issue("s", "S", {"acct": "A"}, run))
    out = _run(tool["handler"]({"ticket": t, "agent": "acct", "task": "x"}, ctx))
    assert "từ plugin" in out


# --------------------------------------------- integration: through main's workflow helpers

def _brain(tmp_path, monkeypatch, can_ask_line):
    import main

    brain = tmp_path / "brain"
    (brain / "agents").mkdir(parents=True)
    agents = {
        "sales": ("Bảo Ngọc", can_ask_line),
        "acct": ("Minh Châu", "can_ask: [sales]\n"),
        "hr": ("Thanh Mai", ""),
    }
    for slug, (name, extra) in agents.items():
        (brain / "agents" / f"{slug}.md").write_text(
            f"---\ntype: agent\nname: {name}\nslug: {slug}\nrole: r\nskills: []\n{extra}---\nthân\n",
            encoding="utf-8")

    engines = []

    class FakeEngine:
        def __init__(self, system_prompt="", allowed_tools=None, **k):
            self.system_prompt = system_prompt
            self.allowed_tools = allowed_tools
            self.model = None
            engines.append(self)

        async def query(self, prompt):
            m = re.search(r"ask_ticket=(ak_\S+)", self.system_prompt)
            if m:
                # Simulate the model calling the tool mid-step, then using the answer.
                ans = await ad.ask(m.group(1), "acct", "soát số giúp")
                yield {"type": "final", "content": f"BÁO GIÁ + {ans}"}
                return
            yield {"type": "final", "content": f"trả lời của {prompt[:20]}"}

    monkeypatch.setattr(main, "claude_engine", lambda **k: FakeEngine(**k))
    monkeypatch.setattr(main, "_brain_root", lambda b: str(brain))
    monkeypatch.setattr(main, "_agents_dir", lambda b: brain / "agents")
    monkeypatch.setattr(main, "_agent_memory", lambda b, s: "")
    logged = []
    monkeypatch.setattr(main, "_log_agent_run", lambda b, s, t, o: logged.append((s, t)))
    return main, engines, logged


def test_step_agent_gets_ticket_only_when_delegating(tmp_path, monkeypatch):
    main, _engines, _logged = _brain(tmp_path, monkeypatch, "can_ask: [acct, ghost, sales]\n")
    _mk, sysprompt, _log, _learn = main._workflow_agent_helpers("brain", None)
    _n, step_sp, _m, _p = sysprompt("sales", delegate=True)
    assert ad.ticket_in(step_sp) and "`acct`: Minh Châu" in step_sp
    # missing file and self are dropped from the list
    assert "ghost" not in step_sp.split("# Nhờ đồng nghiệp")[1].split("Luôn truyền")[0]
    assert "`sales`" not in step_sp
    # default build (direct chat, team chat, verifier, colleague) never carries a ticket
    assert not ad.ticket_in(sysprompt("sales")[1])
    # an agent without can_ask gets no ticket even when delegating
    assert not ad.ticket_in(sysprompt("hr", delegate=True)[1])


def test_step_asks_colleague_one_level_and_logs(tmp_path, monkeypatch):
    main, engines, logged = _brain(tmp_path, monkeypatch, "can_ask: [acct]\n")
    mk, sysprompt, log_run, learn = main._workflow_agent_helpers("brain", None)
    _n, sp, model, prov = sysprompt("sales", delegate=True)

    async def go():
        out = ""
        async for ev in mk(sp, model, prov).query("lập báo giá"):
            if ev["type"] == "final":
                out = ev["content"]
        return out

    out = _run(go())
    assert "Kết quả từ Minh Châu" in out and "trả lời của" in out
    # the colleague's engine was built without a ticket (one level only), even though acct's own
    # file lists can_ask
    assert len(engines) == 2 and not ad.ticket_in(engines[1].system_prompt)
    assert any(s == "acct" and "được Bảo Ngọc nhờ" in t for s, t in logged)


def test_gated_run_grants_ask_tool_to_ticket_holder_only(tmp_path, monkeypatch):
    main, engines, _logged = _brain(tmp_path, monkeypatch, "can_ask: [acct]\n")
    monkeypatch.setattr(main, "_empty_mcp_file", lambda: "")
    mk, sysprompt, _log, _learn = main._workflow_agent_helpers("brain", ["Read"], "auto")
    caller = mk(sysprompt("sales", delegate=True)[1])
    plain = mk(sysprompt("hr")[1])
    assert any(t.endswith("__" + ad.TOOL_NAME) for t in caller.allowed_tools)
    assert not any(ad.TOOL_NAME in t for t in plain.allowed_tools)


def test_colleague_holding_callers_ticket_cannot_ask_onward():
    """Even if the caller pastes its ticket into the task, the colleague cannot spend it while
    it is answering: one level only."""
    nested = []
    holder = {}

    async def run(target, prompt):
        nested.append(await ad.ask(holder["t"], "hr", "nhờ tiếp"))
        return "xong", ""

    holder["t"] = _ticket(ad.issue("s", "S", {"acct": "A", "hr": "H"}, run))
    out = _run(ad.ask(holder["t"], "acct", f"việc, vé ask_ticket={holder['t']}"))
    assert "xong" in out and nested and nested[0].startswith("ERROR")
    # the ticket is free again for the caller's next ask
    assert "xong" in _run(ad.ask(holder["t"], "acct", "việc 2"))


def test_revoked_ticket_refused():
    async def run(target, prompt):
        return "ok", ""

    block = ad.issue("s", "S", {"acct": "A"}, run)
    ad.revoke_in(block)
    assert _run(ad.ask(_ticket(block), "acct", "t")).startswith("ERROR")


def test_graph_step_revokes_ticket_when_it_ends(tmp_path, monkeypatch):
    main, _engines, _logged = _brain(tmp_path, monkeypatch, "can_ask: [acct]\n")
    mk, sysprompt, log_run, learn = main._workflow_agent_helpers("brain", None)
    issued = []
    real_issue = ad.issue
    monkeypatch.setattr(ad, "issue", lambda *a: issued.append(real_issue(*a)) or issued[-1])

    class Node:
        agent = "sales"
        verify_agent = ""
        max_retries = 0
        id = "n1"
        metadata = {}

    async def sink(_ev):
        pass

    res = _run(main._run_workflow_step(Node(), "lập báo giá", mk, sysprompt, sink))
    assert "Kết quả từ Minh Châu" in res["output"]
    assert issued and _run(ad.ask(_ticket(issued[0]), "acct", "sau khi xong")).startswith("ERROR")


def test_codex_profile_waits_longer_than_an_ask():
    import mcp_hub
    assert mcp_hub._ask_tool_timeout() > ad.ASK_TIMEOUT_S


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
