"""Regression: a scheduled background job on Codex gets the Javis hub, or fails for real.

Canary 2026-10-08/09 (one VPS, 0.84.4 to 0.86.102, two read-only scheduled reminders): 4 of 12 runs had no
`mcp__javis__*` tool. Codex 0.161.0 waits only `mcp_optional_startup_grace_ms` (default 1 s,
codex-mcp/src/mcp/mod.rs) for an MCP server that is not `required`, then drops that server from
the turn (codex-mcp/src/connection_manager/tool_catalog.rs). The hub answers `tools/list` in
about 2 s once its 60 s discovery cache has expired. The model then went through the ChatGPT
apps (`mcp__codex_apps__*`) or said it could not work, and the reminder still recorded success.

Fix, for the scheduled background lanes only (reminder, loop, Kanban dispatch):
  - `mcp_servers.javis.required=true`: Codex waits for the hub up to `startup_timeout_sec`, and
    `codex exec` exits with "required MCP servers failed to initialize" when it cannot start;
  - `features.apps=false`: no `codex_apps` server, so no route around the hub;
  - the background engine chain stops on that error instead of handing the prompt to the next
    engine, which would reach the same hub and run blind;
  - claude_cli.codex_error_text puts the reason first: Codex's stderr starts with long rmcp log
    lines, and the chat card keeps 300 characters, reminders.json 400.
Chat never goes through `_build_codex`; workflow Codex agents are built by
main._workflow_agent_helpers. Both must stay unchanged.
Runs on both trees: upstream (hub header from the shared profile) and the Afftera fork, which also
sends each job's permission level (0.84.5, `codex_mode_override`); the mode checks follow the tree.

    python tests/run.py codex_background_hub_required      (no network, does not spawn codex)
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import re
import sys
import tempfile
import time
import tomllib
from pathlib import Path

# Hard-set, not setdefault: inside the production container JAVIS_STATE_DIR, BRAINS_DIR and HOME
# point at live data, and this test writes a Codex profile under HOME and a reminders.json.
_TMP = Path(tempfile.mkdtemp(prefix="javis-codex-bg-hub-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["JAVIS_SESSIONS_DB"] = str(_TMP / "conversations.db")
os.environ["BRAINS_DIR"] = str(_TMP / "brains")
os.environ["HOME"] = str(_TMP / "home")
os.environ.pop("JAVIS_CODEX_SANDBOX", None)
os.environ.pop("CODEX_HOME", None)
for _d in ("state", "brains/Brain Default/Javis", "home"):
    (_TMP / _d).mkdir(parents=True, exist_ok=True)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import claude_cli  # noqa: E402
import config as cfgmod  # noqa: E402
import mcp_hub  # noqa: E402
import aux_engine  # noqa: E402
import reminders  # noqa: E402

claude_cli.find_codex_cli = lambda: "codex"   # CI has no codex binary

fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# Names read with getattr so this file still runs (and turns RED) on a tree without the fix.
REQ_KEY = getattr(mcp_hub, "CODEX_REQUIRED_KEY", "mcp_servers.javis.required")
APPS_KEY = getattr(mcp_hub, "CODEX_APPS_KEY", "features.apps")
REQ_FAIL = getattr(claude_cli, "CODEX_REQUIRED_FAIL", "required MCP servers failed to initialize")
HUB_REQ = getattr(mcp_hub, "dat_codex_hub_bat_buoc", None)
APPS_OFF = getattr(mcp_hub, "dat_codex_tat_app", None)
BRAIN = _TMP / "brains" / "Brain Default"
# Fork 0.84.5 sends the job's level per process; upstream keeps the profile's "full" for every lane.
HAS_JOB_MODE = hasattr(mcp_hub, "codex_mode_override")
want_mode = (lambda m: m) if HAS_JOB_MODE else (lambda m: "full")
CODEX_SPEC = {"provider": aux_engine.CODEX, "model": "gpt-5.5"}


def effective_config(argv):
    """Replay Codex: load the profile picked by -p, then apply every -c in argv order."""
    cfg = {}
    if "-p" in argv:
        name = argv[argv.index("-p") + 1]
        cfg = tomllib.loads((Path.home() / ".codex" / f"{name}.config.toml").read_text(encoding="utf-8"))
    for i, a in enumerate(argv):
        if a != "-c" or i + 1 >= argv.index("exec"):
            continue
        key, raw = argv[i + 1].split("=", 1)
        try:
            val = tomllib.loads(f"v = {raw}")["v"]
        except tomllib.TOMLDecodeError:
            val = raw
        cur, path = cfg, key.strip().split(".")
        for part in path[:-1]:
            if not isinstance(cur.get(part), dict):
                cur[part] = {}
            cur = cur[part]
        cur[path[-1]] = val
    return cfg


def hub_entry(cfg):
    return (cfg.get("mcp_servers") or {}).get("javis") or {}


def count(argv, key):
    return sum(1 for a in argv if str(a).startswith(key + "="))


def shared_profile():
    """What main._write_codex_profile does when the hub is on: one shared file, always full."""
    return mcp_hub.codex_profile("full")


class _Engine:
    """Stand-in for the Claude engine a background lane builds before the router swaps it."""

    def __init__(self, mode=None, tag="reminder"):
        self.cwd = str(BRAIN)
        self.tag = tag
        self.system_prompt = None
        self.javis_vault = str(BRAIN)
        self.javis_mode = mode
        self.model = None

    def is_available(self):
        return True


def set_hub(on):
    cfgmod.SETTINGS_PATH.write_text(json.dumps({"mcp": {"hub": bool(on)}}), encoding="utf-8")


set_hub(True)

# ---- 1. The two overrides: replace, never stack -----------------------------------------------
check("helpers dat_codex_hub_bat_buoc / dat_codex_tat_app exist", HUB_REQ is not None and APPS_OFF is not None)
MODE_OV = mcp_hub.codex_mode_override("auto") if HAS_JOB_MODE else 'mcp_servers.javis.http_headers.X-Javis-Vault="/b"'
extra = ["model_reasoning_effort=high", f"{REQ_KEY}=false", f"{APPS_KEY}=true", MODE_OV]
if HUB_REQ and APPS_OFF:
    for _ in range(3):
        HUB_REQ(extra)
        APPS_OFF(extra)
check("one required override left, and it is true", [x for x in extra if x.startswith(REQ_KEY + "=")] == [f"{REQ_KEY}=true"], extra)
check("one apps override left, and it is false", [x for x in extra if x.startswith(APPS_KEY + "=")] == [f"{APPS_KEY}=false"], extra)
check("other overrides untouched (model, header override)",
      "model_reasoning_effort=high" in extra and MODE_OV in extra, extra)

# ---- 2. Scheduled background lanes: hub required, apps off, per-job mode kept (F2) -------------
BG_TAGS = ("reminder", "loop", "dispatch:t_7a1c:run", "reminder-main", "dispatch:t_7a1c:run-main")
for tag in BG_TAGS:
    for m in ("suggest", "auto", "full"):
        argv = aux_engine._build_codex(CODEX_SPEC, _Engine(tag=tag), m, tag, shared_profile)._build_args()
        cfg = effective_config(argv)
        j = hub_entry(cfg)
        h = j.get("http_headers") or {}
        check(f"{tag} {m}: hub entry is required", j.get("required") is True, sorted(j))
        check(f"{tag} {m}: startup_timeout_sec still 20 from the profile", j.get("startup_timeout_sec") == 20)
        check(f"{tag} {m}: ChatGPT apps switched off", (cfg.get("features") or {}).get("apps") is False)
        check(f"{tag} {m}: hub receives X-Javis-Mode={want_mode(m)} (per-job level kept where the tree has it)",
              h.get("X-Javis-Mode") == want_mode(m))
        check(f"{tag} {m}: auth still comes from the profile", str(h.get("Authorization", "")).startswith("Bearer "))
        check(f"{tag} {m}: exactly one required and one apps override",
              count(argv, REQ_KEY) == 1 and count(argv, APPS_KEY) == 1)

# ---- 3. Every other lane is unchanged: no required, apps untouched, mode override as before ----
for tag in ("workflow", "workflow-main", "ingest", "reply-policy", "reply-policy-review", "learn-gate", "aux", "chat"):
    argv = aux_engine._build_codex(CODEX_SPEC, _Engine(tag=tag), "suggest", tag, shared_profile)._build_args()
    cfg = effective_config(argv)
    check(f"{tag}: hub not marked required", "required" not in hub_entry(cfg))
    check(f"{tag}: apps feature untouched", "apps" not in (cfg.get("features") or {}))
    check(f"{tag}: mode header unchanged ({want_mode('suggest')})",
          (hub_entry(cfg).get("http_headers") or {}).get("X-Javis-Mode") == want_mode("suggest"))

# ---- 4. Shared profile (read by chat lanes) never carries the background overrides -------------
prof = Path.home() / ".codex" / f"{mcp_hub.codex_profile_name()}.config.toml"
before = prof.read_bytes()
aux_engine._build_codex(CODEX_SPEC, _Engine(), "suggest", "reminder", shared_profile)
after = tomllib.loads(prof.read_text(encoding="utf-8"))
check("shared profile: hub not required", "required" not in after["mcp_servers"]["javis"])
check("shared profile: no features table", "features" not in after)
check("shared profile bytes unchanged by a background job", prof.read_bytes() == before)

# ---- 5. No hub profile or hub off: no override, or Codex refuses to start ("invalid transport") -
for label, writer in (("no profile writer", None), ("writer returned nothing", lambda: None)):
    argv = aux_engine._build_codex(CODEX_SPEC, _Engine(), "suggest", "reminder", writer)._build_args()
    check(f"{label}: no required override", count(argv, REQ_KEY) == 0, argv)
    check(f"{label}: no apps override", count(argv, APPS_KEY) == 0, argv)
set_hub(False)
argv = aux_engine._build_codex(CODEX_SPEC, _Engine(), "suggest", "reminder", lambda: "javis")._build_args()
check("hub off in settings: no required and no apps override", count(argv, REQ_KEY) == 0 and count(argv, APPS_KEY) == 0, argv)
set_hub(True)

# ---- 6. strip_tools never leaves `required` without a hub entry ---------------------------------
cc = aux_engine._build_codex(CODEX_SPEC, _Engine(), "suggest", "reminder", shared_profile)
argv = aux_engine.strip_tools(cc, object())._build_args()
check("strip_tools: no profile, mcp_servers wiped", "-p" not in argv and "mcp_servers={}" in argv, argv)
check("strip_tools: required override removed with the hub", count(argv, REQ_KEY) == 0, argv)

# ---- 7. Through the router a reminder really uses ------------------------------------------------
for m in ("suggest", "auto", "full"):
    out = aux_engine.swap(_Engine(mode=m), mode=m, tag="reminder", spec=CODEX_SPEC,
                          codex_profile=shared_profile, settings={})
    links = out._all() if hasattr(out, "_all") else [out]
    codex = [e for e in links if isinstance(e, claude_cli.CodexCLI)]
    cfg = effective_config(codex[0]._build_args()) if codex else {}
    check(f"swap({m}): Codex link has the hub required and apps off",
          hub_entry(cfg).get("required") is True and (cfg.get("features") or {}).get("apps") is False)
    check(f"swap({m}): Codex link reaches the hub at {want_mode(m)}",
          (hub_entry(cfg).get("http_headers") or {}).get("X-Javis-Mode") == want_mode(m))
    shape_ok = len(links) == 1 if m == "full" else (len(links) >= 2 and links[0] is codex[0])
    check(f"swap({m}): chain shape unchanged (full has no fallback, others Codex first)", shape_ok,
          [type(x).__name__ for x in links])


# ---- 8. The chain stops on a required-hub failure, and only on that -----------------------------
class FakeEngine:
    def __init__(self, events, provider=None):
        self.events, self.ran, self.session_id = events, 0, None
        if provider:
            self.provider = provider

    def is_available(self):
        return True

    def reset_session(self):
        self.session_id = None

    async def query(self, prompt):
        self.ran += 1
        for ev in self.events:
            yield ev


async def collect(engine):
    return [ev async for ev in engine.query("lam viec")]


FB = aux_engine._FallbackChain
FINAL = lambda s: {"type": "final", "content": s}
# The exact stderr codex-cli 0.161.0 printed in the isolated probe of the 0.86.103 preflight (hub
# never answered initialize, startup_timeout_sec = 20), through Javis's own error formatter, as
# CodexCLI.query does when Codex exits non-zero. The rmcp log line comes first.
REQ_STDERR = [
    "2026-10-09T00:20:19.720107Z ERROR rmcp::transport::worker: worker quit with fatal: Transport channel closed, "
    "when Client(HttpRequest(HttpRequest(\"http/request failed: error sending request for url "
    "(http://127.0.0.1:19310/hub/mcp)\")))",
    "2026-10-09T00:20:19.722743Z ERROR codex_core::session: Failed to create session: required MCP servers failed "
    "to initialize: javis: timed out handshaking with MCP server after 20s",
    "Error: thread/start: thread/start failed: error creating thread: Fatal error: Failed to initialize session: "
    "required MCP servers failed to initialize: javis: timed out handshaking with MCP server after 20s (code -32603)",
]
REQ_ERR = claude_cli.codex_error_text(1, REQ_STDERR)
# Hub port closed: same probe, the reason line is ~800 characters of transport detail.
DOWN_STDERR = [
    REQ_STDERR[0],
    "2026-10-09T00:19:58.391560Z ERROR codex_core::session: Failed to create session: required MCP servers failed to "
    "initialize: javis: handshaking with MCP server failed: Send message error Transport "
    "[codex_rmcp_client::event_notification_transport::EventNotificationTransport<rmcp::transport::worker::"
    "WorkerTransport<rmcp::transport::streamable_http_client::StreamableHttpClientWorker<codex_rmcp_client::"
    "http_client_adapter::StreamableHttpClientAdapter>>>] error: Client error: HTTP request failed: http/request "
    "failed: error sending request for url (http://127.0.0.1:19300/hub/mcp), when send initialize request",
]
for label, lines in (("hub hung (timed out after 20s)", REQ_STDERR), ("hub port closed", DOWN_STDERR)):
    txt = claude_cli.codex_error_text(1, lines)
    check(f"codex_error_text, {label}: reason within the first 300 characters", REQ_FAIL in txt[:300], txt[:300])
    check(f"codex_error_text, {label}: names the hub server and keeps the exit code", "javis:" in txt and "1" in txt)
    check(f"codex_error_text, {label}: bounded length", len(txt) < 600, len(txt))
other = claude_cli.codex_error_text(2, ["Error: unexpected status 401 Unauthorized"])
check("codex_error_text, unrelated error: old format kept", other.startswith("Codex lỗi (exit 2):") and "401" in other, other)
BLIND = "Không thấy tool google-workspace__search_gmail_messages nên chưa đọc được thư."

codex = FakeEngine([{"type": "error", "content": REQ_ERR}], provider="openai-oauth")
claude = FakeEngine([FINAL(BLIND)])
evs = asyncio.run(collect(FB([codex, claude])))
check("required hub failed: the chain returns that error", bool(evs) and evs[-1].get("type") == "error"
      and REQ_FAIL in evs[-1].get("content", ""), evs)
check("required hub failed: next engine NOT run (it would reach the same hub blind)", claude.ran == 0)
check("required hub failed: no final leaks out", all(e.get("type") != "final" for e in evs))
check("required hub failed: the reason is in the first 300 characters (what the chat card keeps)",
      bool(evs) and REQ_FAIL in str(evs[-1].get("content", ""))[:300], str(evs[-1].get("content", ""))[:300] if evs else "")
check("required hub failed: Codex's own line is kept (javis + timed out after 20s)",
      bool(evs) and "javis: timed out handshaking with MCP server after 20s" in str(evs[-1].get("content", "")))

codex = FakeEngine([{"type": "error", "content": "Codex: You've hit your usage limit."}], provider="openai-oauth")
claude = FakeEngine([FINAL("claude cứu")])
evs = asyncio.run(collect(FB([codex, claude])))
check("other Codex errors (quota) still fall back to Claude", evs[-1] == FINAL("claude cứu") and claude.ran == 1)

codex = FakeEngine([{"type": "tool_call", "name": "mcp__javis__javis_run_tool"}, FINAL("xong")], provider="openai-oauth")
claude = FakeEngine([FINAL("không được chạy")])
evs = asyncio.run(collect(FB([codex, claude])))
check("healthy Codex run: unchanged, Claude never runs", evs[-1] == FINAL("xong") and claude.ran == 0)

# ---- 9. End to end at the reminder layer: a missing hub is a FAILED job, not a done one ---------
REM_FILE = BRAIN / "Javis" / "reminders.json"
sent = []


async def send(chat_id, text, viec=None, web=None):
    sent.append({"chat_id": chat_id, "text": text, "viec": viec})
    return True, ""


def run_fire(chain_engines):
    rem = {"id": "r_hubreq01", "mode": "task", "text": "Đọc Gmail qua hub, chỉ đọc.", "label": "reminder test",
           "muc_quyen": "suggest", "cron": "30 */6 * * *", "status": "pending",
           "due_at": time.time() - 5, "fired_at": 0, "chat_id": "web:test", "result": "", "error": ""}
    REM_FILE.write_text(json.dumps({"reminders": [rem], "updated": 0}), encoding="utf-8")
    sent.clear()
    feat = reminders.RemindersFeature(reminders.RemindersDeps(
        brain_root=lambda b: str(BRAIN),
        atomic_write_text=lambda p, t: Path(p).write_text(t, encoding="utf-8"),
        send_telegram=send,
        build_system_prompt=lambda b: "",
        aux_model=lambda: None,
        safe_tools=[],
        readonly_tools=[],
        scheduler_brains=lambda: ["Brain Default"],
        aux_swap=lambda cli, mode=None, tag=None: FB(list(chain_engines)),
    ))
    asyncio.run(feat._fire("Brain Default", dict(rem)))
    return json.loads(REM_FILE.read_text(encoding="utf-8"))["reminders"][0]


def run_fire_single(engine):
    """Same as run_fire, at muc_quyen full: the router hands back the Codex engine itself."""
    rem = {"id": "r_hubreq02", "mode": "task", "text": "Đọc số liệu qua hub.", "label": "full test", "muc_quyen": "full",
           "cron": "0 */6 * * *", "status": "pending", "due_at": time.time() - 5, "fired_at": 0,
           "chat_id": "", "result": "", "error": ""}
    REM_FILE.write_text(json.dumps({"reminders": [rem], "updated": 0}), encoding="utf-8")
    sent.clear()
    feat = reminders.RemindersFeature(reminders.RemindersDeps(
        brain_root=lambda b: str(BRAIN),
        atomic_write_text=lambda p, t: Path(p).write_text(t, encoding="utf-8"),
        send_telegram=send, build_system_prompt=lambda b: "", aux_model=lambda: None,
        safe_tools=[], readonly_tools=[], scheduler_brains=lambda: ["Brain Default"],
        aux_swap=lambda cli, mode=None, tag=None: engine,
    ))
    asyncio.run(feat._fire("Brain Default", dict(rem)))
    return json.loads(REM_FILE.read_text(encoding="utf-8"))["reminders"][0]


codex = FakeEngine([{"type": "error", "content": REQ_ERR}], provider="openai-oauth")
claude = FakeEngine([FINAL(BLIND)])
stored = run_fire([codex, claude])
check("reminder: error recorded with the Codex required-hub message", REQ_FAIL in (stored.get("error") or ""), stored.get("error"))
check("reminder: no result text (not a blind 'done')", (stored.get("result") or "") == "", stored.get("result"))
check("reminder: Claude was not asked to run the job blind", claude.ran == 0)
check("reminder: chat card status is failed", bool(sent) and (sent[-1]["viec"] or {}).get("status") == "failed", sent[-1:])
check("reminder: message to the owner is a warning", bool(sent) and sent[-1]["text"].startswith("⚠"), sent[-1:])
check("reminder: the warning names the reason", bool(sent) and REQ_FAIL in sent[-1]["text"], sent[-1:])
check("reminder: cron job stays scheduled for its next run", stored.get("status") == "pending" and stored.get("due_at", 0) > time.time())

# Full level: swap returns the Codex engine alone (no fallback chain), the error must still be readable.
codex = FakeEngine([{"type": "error", "content": REQ_ERR}], provider="openai-oauth")
stored = run_fire_single(codex)
check("reminder at full (no chain): error recorded with the reason", REQ_FAIL in (stored.get("error") or ""), stored.get("error"))
check("reminder at full (no chain): card failed and warning names the reason",
      bool(sent) and (sent[-1]["viec"] or {}).get("status") == "failed" and REQ_FAIL in sent[-1]["text"], sent[-1:])

codex = FakeEngine([{"type": "tool_call", "name": "mcp__javis__javis_run_tool"}, FINAL("OK: 3 rows")], provider="openai-oauth")
claude = FakeEngine([FINAL("không được chạy")])
stored = run_fire([codex, claude])
check("reminder healthy run: result kept, no error, card done",
      stored.get("result") == "OK: 3 rows" and not stored.get("error")
      and bool(sent) and (sent[-1]["viec"] or {}).get("status") == "done")

# ---- 10. Scope: only the background router sets these overrides --------------------------------
SRC = {p.name: p.read_text(encoding="utf-8") for p in SERVER.glob("*.py")}
users = sorted(n for n, s in SRC.items() if "dat_codex_hub_bat_buoc(" in s or "dat_codex_tat_app(" in s)
check("only mcp_hub (definition) and aux_engine (_build_codex) use the overrides",
      users == ["aux_engine.py", "mcp_hub.py"], users)
callers = sorted(n for n, s in SRC.items() if re.search(r"\b_build_codex\(", s))
check("_build_codex is only called inside aux_engine (background router)", callers == ["aux_engine.py"], callers)
# The allowlist (reminder, loop, dispatch:*) only works while these lanes keep passing those tags.
REM_SRC, TASK_SRC, LOOP_SRC = SRC.get("reminders.py", ""), SRC.get("tasks.py", ""), SRC.get("self_improve.py", "")
check('reminders still route with tag="reminder"', 'aux_engine.apply(self.deps, cli, mode=mq, tag="reminder")' in REM_SRC)
check("Kanban runs still route with tag dispatch:<id>:<suffix>",
      "tag=f\"dispatch:{task['id']}:" in TASK_SRC and "aux_engine.apply(self.deps, cli, mode=mode, tag=cli.tag)" in TASK_SRC)
check('loops still route with tag="loop"', 'tag="loop")' in LOOP_SRC and "aux_engine.apply(self.deps, cli" in LOOP_SRC)
check("workflow Codex agents still built directly, without the background overrides",
      "CodexCLI(cwd=vault_root, tag=\"workflow\"" in SRC.get("main.py", "")
      and "CODEX_REQUIRED_KEY" not in SRC.get("main.py", "") and "dat_codex_tat_app" not in SRC.get("main.py", ""))

print(("RED: " + str(len(fails))) if fails else "GREEN: all checks passed")
sys.exit(1 if fails else 0)
