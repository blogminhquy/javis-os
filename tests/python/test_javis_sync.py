"""Javis Sync: Claude Code and Codex sessions saved into Javis automatically (owner, 20/11/2026).

    python tests/run.py javis_sync -v      (no network)

The Gate tools only save what an outside AI chooses to send, so Claude Code and Codex sessions never reached Javis.
`tools/javis-sync/javis_sync.py` runs as a Claude Code Stop hook and as Codex's notify program and posts each finished
turn to POST /chat/external (`chat_bridge.log_transcript`). This file locks:

1. The route saves turns through the normal save path (History, conversation log, learning queue) into one
   conversation per outside session, with the Gate source block, without running any engine.
2. A resent turn (same id) is never saved twice; secrets are masked; bad input is a 400; a conversation the owner is
   chatting in right now is a 409 and nothing is lost.
3. The hook reads a real-shaped Claude Code transcript: prompts and final answers only, no tool calls, no sidechains,
   slash commands kept as typed; it resumes from where it stopped and keeps unsent turns for the next run.
4. Codex notify: one turn per call, kept while Javis is unreachable, and an existing notify program is chained.
5. install / uninstall edit ~/.claude/settings.json and ~/.codex/config.toml without losing what was there.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import importlib.util
import json
import os
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-sync-state-")
os.environ["JAVIS_STATE_DIR"] = _STATE
_HOME = Path(tempfile.mkdtemp(prefix="javis-sync-home-"))
os.environ["JAVIS_SYNC_HOME"] = str(_HOME / ".javis-sync")
os.environ["JAVIS_SYNC_CLAUDE_SETTINGS"] = str(_HOME / ".claude" / "settings.json")
os.environ["JAVIS_SYNC_CODEX_CONFIG"] = str(_HOME / ".codex" / "config.toml")
os.environ.pop("JAVIS_SYNC_OFF", None)

import main  # noqa: E402
import chat_bridge as CB  # noqa: E402
import sessions  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info})"))
    if not cond:
        _fails.append(name)


main.cfgmod.gate_active = lambda: False
LOGGED = []
main.log_conversation = lambda brain, u, j: LOGGED.append((u, j))
LEARN = []


async def _learn(brain, sid, u, j):
    LEARN.append(sid)
main.learn_feature.enqueue = _learn
ENGINE_RUNS = []
main._chat_provider = lambda *_a, **_k: ENGINE_RUNS.append(1) or ("openrouter", "api", "k", "m")

st = main.get_store()
OLD = st.create_session(brain="brain", engine="test", model="test", title="An older chat")
client = TestClient(main.app, base_url="http://127.0.0.1:8080")


def post(body):
    r = client.post("/chat/external", json=body)
    return r.status_code, r.json()


# ============================================================
# 1. The route
# ============================================================
code, out = post({"check": True})
check("check: answers ok and lists the sources without saving", code == 200 and out.get("ok")
      and out.get("sources") == ["claude-code", "codex"], out)

turns = [{"id": "u1", "user": "Sửa lỗi đăng nhập trang admin", "assistant": "Đã sửa, lỗi ở session cookie."},
         {"id": "u2", "user": "Key là sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345 nhé", "assistant": "Ok."}]
before = len(st.list_sessions(limit=100))
code, out = post({"source": "claude-code", "session": "abc-123", "project": "shop-web", "turns": turns})
check("two turns saved", code == 200 and out.get("saved") == 2 and out.get("skipped") == 0, out)
SID = out.get("id")
row = st.get_session(SID) or {}
check("one new conversation for the outside session", len(st.list_sessions(limit=100)) == before + 1)
check("title says where it came from, the project and the first prompt",
      row.get("title", "").endswith("Claude Code: shop-web: Sửa lỗi đăng nhập trang admin"), row.get("title"))
msgs = st.get_messages(SID)
roles = [m["role"] for m in msgs]
check("stored as prompt/answer pairs", roles == ["user", "assistant", "user", "assistant"], roles)
check("the prompt carries the Gate block, so the dashboard shows 'from Claude Code'",
      CB.nguon_cua(msgs[0]["content"]) == "Claude Code", msgs[0]["content"][:80])
check("the block says the reply was the outside agent's, not Javis's", "not by Javis" in msgs[0]["content"])
check("the answer is the agent's own text", msgs[1]["content"] == "Đã sửa, lỗi ở session cookie.")
check("an API key in a prompt is masked before it is stored",
      "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345" not in msgs[2]["content"] and "sk-ant" in msgs[2]["content"], msgs[2]["content"])
check("went through the normal save path: conversation log", len(LOGGED) == 2, LOGGED)
check("went through the normal save path: learning queue", LEARN.count(SID) == 2, LEARN)
check("no engine ran", not ENGINE_RUNS)
check("the dashboard title strips the block", sessions.title_from_message(msgs[0]["content"])
      == "Sửa lỗi đăng nhập trang admin")

code, out = post({"source": "claude-code", "session": "abc-123", "project": "shop-web",
                  "turns": turns + [{"id": "u3", "user": "tiếp", "assistant": "Xong."}]})
check("a resent request saves only the new turn", code == 200 and out.get("saved") == 1 and out.get("skipped") == 2
      and out.get("id") == SID, out)
check("into the same conversation", len(st.get_messages(SID)) == 6, len(st.get_messages(SID)))

code, out = post({"source": "codex", "session": "abc-123", "turns": [{"id": "x", "user": "hi", "assistant": ""}]})
check("same session id from another agent is another conversation", code == 200 and out.get("id") != SID, out)
check("Codex conversation title", "Codex: " in (st.get_session(out["id"]) or {}).get("title", ""))
msgs_cx = st.get_messages(out["id"])
check("a turn with no text answer still saves, with a note", bool(msgs_cx) and "Codex" in msgs_cx[-1]["content"],
      msgs_cx[-1:] if msgs_cx else None)

big = "x" * (CB.MAX_TRANSCRIPT_TEXT + 500)
code, out = post({"source": "codex", "session": "big", "turns": [{"id": "b", "user": big, "assistant": "ok"}]})
saved_big = st.get_messages(out["id"])[0].get("content", "")
check("a very long prompt is cut with a marker, not refused", code == 200 and "500 more characters" in saved_big
      and len(saved_big) < CB.MAX_TRANSCRIPT_TEXT + 600, len(saved_big))

for body, why in (({"source": "cursor", "session": "a", "turns": []}, "unknown source"),
                  ({"source": "codex", "session": "a b/c", "turns": []}, "bad session id"),
                  ({"source": "codex", "session": "a", "turns": "nope"}, "turns not a list"),
                  ({"source": "codex", "session": "a", "turns": [{}] * (CB.MAX_TRANSCRIPT_TURNS + 1)}, "too many")):
    code, out = post(body)
    check(f"400 on {why}", code == 400 and not out.get("ok"), (code, out))

_orig = CB._dang_chay
CB._dang_chay = lambda sid: sid == SID
code, out = post({"source": "claude-code", "session": "abc-123", "turns": [{"id": "u4", "user": "a", "assistant": "b"}]})
CB._dang_chay = _orig
check("409 busy while the owner chats in that conversation", code == 409 and out.get("busy"), (code, out))
code, out = post({"source": "claude-code", "session": "abc-123", "turns": [{"id": "u4", "user": "a", "assistant": "b"}]})
check("the same turn saves once the owner is done", code == 200 and out.get("saved") == 1, out)

check("a chat-scope API token reaches the route (it lives under /chat)",
      main.cfgmod.TOKEN_SCOPE_CHAT[0] == "/chat" and "/chat/external".startswith("/chat/"))

# ============================================================
# 2. The hook script
# ============================================================
spec = importlib.util.spec_from_file_location("javis_sync", ROOT / "tools" / "javis-sync" / "javis_sync.py")
JS = importlib.util.module_from_spec(spec)
spec.loader.exec_module(JS)

SENT = []
DOWN = {"v": False}


def fake_post(cfg, body):
    if DOWN["v"]:
        raise JS.SendError("cannot reach http://javis: refused")
    SENT.append(body)
    r = client.post("/chat/external", json=body)
    data = r.json()
    if r.status_code != 200:
        raise JS.SendError(f"HTTP {r.status_code}: {data.get('error')}")
    return data
JS.post = fake_post


def line(**kw):
    return json.dumps(kw, ensure_ascii=False)


def user(uuid, content, **kw):
    return line(type="user", uuid=uuid, message={"role": "user", "content": content}, **kw)


def asst(uuid, *blocks, **kw):
    return line(type="assistant", uuid=uuid, message={"role": "assistant", "content": list(blocks)}, **kw)


T = lambda s: {"type": "text", "text": s}  # noqa: E731
TOOL = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}
transcript = [
    line(type="summary", summary="old"),
    user("p0", "Caveat: local commands below", isMeta=True),
    user("p1", "Thêm nút xuất Excel cho trang đơn hàng"),
    asst("a1", T("Để em xem file trước."), TOOL),
    user("r1", [{"type": "tool_result", "tool_use_id": "t1", "content": "app.py"}], toolUseResult={"stdout": "app.py"}),
    asst("a2", T("Em đã thêm nút Xuất Excel ở góc phải.")),
    asst("a3", T("Chạy test xanh hết.")),
    user("s1", "subagent prompt", isSidechain=True),
    asst("s2", T("subagent answer"), isSidechain=True),
    user("p2", "<command-name>/review</command-name>\n<command-message>review</command-message>\n<command-args>PR 12</command-args>"),
    asst("a4", T("Review xong, không có lỗi.")),
    user("p3", "<local-command-stdout>ok</local-command-stdout>"),
    user("p4", "[Request interrupted by user]"),
    user("p5", [T("Ảnh lỗi đây"), {"type": "image", "source": {}}]),
    asst("a5", TOOL),
]
parsed = JS.parse_claude(transcript)
check("transcript: three prompts, meta/tool result/sidechain/local output/interrupt skipped",
      [t["id"] for t in parsed] == ["p1", "p2", "p5"], [t["id"] for t in parsed])
check("the answer is the text after the last tool call, not the 'let me look' line",
      parsed[0]["assistant"] == "Em đã thêm nút Xuất Excel ở góc phải.\n\nChạy test xanh hết.", parsed[0]["assistant"])
check("a slash command is kept as typed", parsed[1]["user"] == "/review PR 12", parsed[1]["user"])
check("an attached image is mentioned", parsed[2]["user"].endswith("[1 image(s) attached]"), parsed[2]["user"])
check("a turn that ended on a tool call has no answer yet", parsed[2]["assistant"] == "", parsed[2])

proj = _HOME / "work" / "orders-app"
proj.mkdir(parents=True)
tpath = _HOME / "t.jsonl"
tpath.write_text("\n".join(transcript) + "\n", encoding="utf-8")


def run_hook(session="cc-1"):
    import io
    import sys
    old = sys.stdin
    sys.stdin = io.StringIO(json.dumps({"session_id": session, "transcript_path": str(tpath), "cwd": str(proj),
                                        "hook_event_name": "Stop"}))
    try:
        return JS.main(["claude"])
    finally:
        sys.stdin = old


JS.write_json(JS.CONFIG, {"url": "http://javis", "token": "jvs_x"})
rc = run_hook()
check("hook exits 0", rc == 0)
check("hook sent the answered turns, held back the one still waiting for its answer",
      len(SENT) == 1 and [t["id"] for t in SENT[0]["turns"]] == ["p1", "p2"], SENT)
check("hook names the project from cwd", SENT and SENT[0]["project"] == "orders-app")
with tpath.open("a", encoding="utf-8") as f:
    f.write(asst("a6", T("Đã thấy lỗi trong ảnh, sửa xong.")) + "\n")
SENT.clear()
run_hook()
check("next run resumes: only the held-back turn, now with its answer",
      len(SENT) == 1 and [(t["id"], t["assistant"]) for t in SENT[0]["turns"]]
      == [("p5", "Đã thấy lỗi trong ảnh, sửa xong.")], SENT)
SENT.clear()
run_hook()
check("nothing new, nothing sent", not SENT, SENT)

with tpath.open("a", encoding="utf-8") as f:
    f.write(user("p6", "deploy đi") + "\n" + asst("a7", T("Đã deploy.")) + "\n")
DOWN["v"] = True
run_hook()
DOWN["v"] = False
check("Javis down: hook still exits quietly and logs it", "refused" in JS.LOG.read_text(encoding="utf-8"))
run_hook()
check("within the back-off window nothing is tried", not SENT, SENT)
st_ = JS.read_json(JS.STATE, {})
st_.pop("last_fail", None)
JS.write_json(JS.STATE, st_)
run_hook()
check("after the back-off the waiting turn is sent", SENT and SENT[-1]["turns"][0]["id"] == "p6", SENT)

SENT.clear()
cfg_x = JS.read_json(JS.CONFIG, {})
JS.write_json(JS.CONFIG, {**cfg_x, "exclude": [str(_HOME / "work")]})
with tpath.open("a", encoding="utf-8") as f:
    f.write(user("p7", "bí mật") + "\n" + asst("a8", T("ok")) + "\n")
run_hook()
check("an excluded folder is never sent", not SENT, SENT)
JS.write_json(JS.CONFIG, cfg_x)

# Codex notify
ev = {"type": "agent-turn-complete", "thread-id": "th-9", "turn-id": "turn-1", "cwd": str(proj),
      "input-messages": ["Viết test cho hàm tính thuế"], "last-assistant-message": "Đã viết 5 test, xanh hết."}
SENT.clear()
check("codex notify exits 0", JS.main(["codex", json.dumps(ev, ensure_ascii=False)]) == 0)
check("codex turn sent", SENT and SENT[0]["source"] == "codex" and SENT[0]["session"] == "th-9"
      and SENT[0]["turns"][0]["assistant"] == "Đã viết 5 test, xanh hết.", SENT)
DOWN["v"] = True
JS.main(["codex", json.dumps({**ev, "turn-id": "turn-2"})])
DOWN["v"] = False
check("codex turn kept while Javis is down", len(JS.read_json(JS.STATE, {}).get("codex_pending") or []) == 1)
st_ = JS.read_json(JS.STATE, {})
st_.pop("last_fail", None)
JS.write_json(JS.STATE, st_)
SENT.clear()
JS.main(["codex", json.dumps({**ev, "turn-id": "turn-3"})])
check("the kept turn goes out with the next one", SENT and [t["id"] for t in SENT[0]["turns"]] == ["turn-2", "turn-3"],
      SENT)
check("nothing left waiting", not JS.read_json(JS.STATE, {}).get("codex_pending"))
check("a non-turn event or garbage never fails", JS.main(["codex", "{not json"]) == 0
      and JS.main(["codex", json.dumps({"type": "other"})]) == 0)

# ============================================================
# 3. install / uninstall
# ============================================================
JS.CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
JS.CLAUDE_SETTINGS.write_text(json.dumps({"model": "opus", "hooks": {"Stop": [
    {"hooks": [{"type": "command", "command": "say done"}]}]}}), encoding="utf-8")
JS.CODEX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
JS.CODEX_CONFIG.write_text('model = "gpt-5.5"\nnotify = ["notify-send", "Codex"]\n\n[mcp_servers.javis]\nurl = "x"\n'
                           'notify = "not top level"\n', encoding="utf-8")
DOWN["v"] = True
check("install refuses a URL/token Javis does not accept",
      JS.main(["install", "--url", "http://bad", "--token", "t"]) == 1 and not JS.CLAUDE_SETTINGS.read_text(
          encoding="utf-8").count("javis_sync.py"))
DOWN["v"] = False
rc = JS.main(["install", "--url", "http://javis/", "--token", "jvs_abc"])
check("install ok", rc == 0)
cfg = json.loads(JS.CONFIG.read_text(encoding="utf-8"))
check("config saved with url and token", cfg.get("url") == "http://javis" and cfg.get("token") == "jvs_abc", cfg)
if os.name != "nt":
    check("config is private (600)", oct(JS.CONFIG.stat().st_mode & 0o777) == "0o600")
check("script copied next to the config", JS.INSTALLED_SCRIPT.is_file())
cs = json.loads(JS.CLAUDE_SETTINGS.read_text(encoding="utf-8"))
cmds = [h["command"] for g in cs["hooks"]["Stop"] for h in g["hooks"]]
check("Claude Code: our Stop hook added, the owner's own hook and settings kept",
      cs.get("model") == "opus" and "say done" in cmds and sum("javis_sync.py" in c for c in cmds) == 1, cmds)
check("Claude Code: a backup of settings.json", JS.CLAUDE_SETTINGS.with_name("settings.json.bak").is_file())
toml = JS.CODEX_CONFIG.read_text(encoding="utf-8")
check("Codex: notify points at the script, as a top-level key", toml.splitlines()[0].startswith("notify = [")
      and "javis_sync.py" in toml.splitlines()[0] and '"codex"]' in toml.splitlines()[0], toml)
check("Codex: the old notify line is gone, the table's own 'notify' key untouched",
      '"notify-send"' not in toml and 'notify = "not top level"' in toml and 'model = "gpt-5.5"' in toml, toml)
check("Codex: the old notify program is chained", cfg.get("codex_chain") == ["notify-send", "Codex"], cfg)
try:
    import tomllib
    tomllib.loads(toml)
    check("Codex: config.toml is still valid TOML", True)
except ImportError:
    pass
except Exception as e:  # noqa: BLE001
    check("Codex: config.toml is still valid TOML", False, e)

JS.main(["install", "--url", "http://javis", "--token", "jvs_abc"])
cs = json.loads(JS.CLAUDE_SETTINGS.read_text(encoding="utf-8"))
toml2 = JS.CODEX_CONFIG.read_text(encoding="utf-8")
check("install twice: still one hook", sum("javis_sync.py" in h["command"] for g in cs["hooks"]["Stop"]
                                           for h in g["hooks"]) == 1)
check("install twice: still one notify, chain kept", toml2.count("javis_sync.py") == 1
      and json.loads(JS.CONFIG.read_text(encoding="utf-8")).get("codex_chain") == ["notify-send", "Codex"])

JS.main(["uninstall"])
cs = json.loads(JS.CLAUDE_SETTINGS.read_text(encoding="utf-8"))
check("uninstall: our hook gone, the owner's kept", [h["command"] for g in cs["hooks"]["Stop"] for h in g["hooks"]]
      == ["say done"], cs)
toml3 = JS.CODEX_CONFIG.read_text(encoding="utf-8")
check("uninstall: Codex notify back to the owner's program", "javis_sync.py" not in toml3
      and toml3.startswith('notify = ["notify-send", "Codex"]'), toml3)

# ============================================================
# 4. "Connecting Gate is the whole setup": the Gate tells a coding agent to offer Javis Sync and hands it the command
# ============================================================
import asyncio  # noqa: E402
import mcp_hub  # noqa: E402

GATE = {"source": "Claude Code"}


def hub(msg, mode="full", gate=GATE):
    return asyncio.get_event_loop().run_until_complete(mcp_hub._handle_one(msg, mode, gate=gate))


asyncio.set_event_loop(asyncio.new_event_loop())
init = hub({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
ins = init["result"].get("instructions") or ""
check("Gate initialize carries instructions to offer Javis Sync",
      "javis_sync_setup" in ins and "~/.javis-sync/config.json" in ins and "ask the owner once" in ins, ins[:200])
check("Javis's own engines get no such instructions",
      "instructions" not in hub({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, gate=None)["result"])


def names(mode):
    return [t["name"] for t in hub({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, mode)["result"]["tools"]]


check("javis_sync_setup at Draft and Full", "javis_sync_setup" in names("auto") and "javis_sync_setup" in names("full"))
check("not at Read only (it mints a token)", "javis_sync_setup" not in names("suggest"))


def setup(args, mode="full"):
    res = hub({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
               "params": {"name": "javis_sync_setup", "arguments": args}}, mode)["result"]
    return res["content"][0]["text"], res["isError"]


cfg0 = main.cfgmod.read_settings()
cfg0.setdefault("domain", {})["custom"] = ""
main.cfgmod.write_settings(cfg0)
os.environ.pop("DOMAIN_NAME", None)
txt, err = setup({})
check("unknown public address: asks the AI for javis_url, mints nothing", err and "javis_url" in txt
      and not [t for t in main.cfgmod.list_api_tokens() if t.get("scope") == "sync"], txt)
txt, err = setup({"javis_url": "javascript:alert(1)"})
check("a javis_url that is not http(s) is refused", err, txt)

cfg0["domain"]["custom"] = "javis.example.com"
main.cfgmod.write_settings(cfg0)
txt, err = setup({})
out = json.loads(txt) if not err else {}
cmd = out.get("command", "")
check("the address comes from the domain in Settings", "--url https://javis.example.com " in cmd, txt[:300])
check("one shell command: download the script and install", cmd.startswith("curl -fsSL https://raw.githubusercontent")
      and "javis_sync.py install" in cmd and out.get("shell") == "sh", cmd)
tok = cmd.split("--token ")[-1].strip()
check("the token is a sync token named after the outside AI", [t["name"] for t in main.cfgmod.list_api_tokens()
                                                               if t.get("scope") == "sync"] == ["Javis Sync (Claude Code)"])
check("a sync token reaches /chat/external", bool(main.cfgmod.verify_api_token(tok, "/chat/external")))
for path in ("/chat", "/chat/jobs", "/sessions", "/sessions/x", "/chat/external/x", "/auth/tokens"):
    check(f"a sync token does NOT reach {path}", not main.cfgmod.verify_api_token(tok, path))
check("the AI is told not to echo the token", "Do not repeat the token" in out.get("how", ""))

txt, err = setup({"system": "Windows", "javis_url": "https://my.javis.vn/"})
out = json.loads(txt) if not err else {}
check("Windows gets a PowerShell command, javis_url wins and loses its trailing slash",
      out.get("shell") == "powershell" and out["command"].startswith("irm ")
      and "--url https://my.javis.vn --token" in out["command"], txt[:300])
txt, err = setup({}, mode="suggest")
check("Read only level is refused with a clear reason", err and "Draft or Full" in txt, txt)

_orig_list = main.cfgmod.list_api_tokens
main.cfgmod.list_api_tokens = lambda: [{"scope": "sync"}] * CB.MAX_SYNC_TOKENS
txt, err = setup({})
main.cfgmod.list_api_tokens = _orig_list
check("too many sync tokens: refused, told where to revoke", err and "API tokens" in txt, txt)
check("dashboard labels the sync scope", 'cs.tk_scope_sync' in (ROOT / "dashboard" / "console.js").read_text(
    encoding="utf-8") and all("cs.tk_scope_sync" in json.loads((ROOT / "dashboard" / "i18n" / f"{lg}.json").read_text(
        encoding="utf-8")) for lg in ("vi", "en")))

check("no em dash in the script", chr(0x2014) not in (ROOT / "tools" / "javis-sync" / "javis_sync.py").read_text(
    encoding="utf-8"))

print()
print("ALL PASS" if not _fails else f"{len(_fails)} FAIL: {_fails}")
raise SystemExit(1 if _fails else 0)
