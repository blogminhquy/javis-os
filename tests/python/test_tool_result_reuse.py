"""Leaner tool results in the API engines' tool loop, with nothing lost for the model (2026-11-17).

    python tests/run.py tool_result_reuse      (no network: the model is a fake server on localhost)

Owner, 17/11/2026: save tokens "mà vừa không ảnh hưởng đến chất lượng kết quả". What this pins:
  1. A byte-identical repeat of the same call (same tool, same arguments) in one turn becomes a one-line reference,
     but the tool still runs every time, so changed data always reaches the model in full.
  2. A reference is never handed out when the earlier copy was trimmed, and when a trim cuts an earlier copy that
     references point to, the full text goes back into the newest reference.
  3. Compact JSON keeps the same value, turns \\uXXXX escapes into characters, and never touches the content tools
     (files, terminal, web, skills) whose output a model may copy or edit exactly.
  4. The Off saving level and the dedicated switch turn the references off.
  5. All three tool loops (Chat Completions, Anthropic Messages, Responses) are wired, and the request a model gets
     after a repeat is really smaller.
  6. CLI engines (Claude Code, Codex) get the same savings at the hub, one record per turn (a warm engine's lane key
     included): whole, reference, whole again, and the record is dropped when Claude Code (PreCompact, through a
     wrapper that leaves claude_sdk_engine.py byte for byte) or Codex (contextCompaction) compacts.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import copy
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-reuse-")
os.environ["JAVIS_API_STREAM_TOOLS"] = "0"   # plain JSON rounds keep the fake server short
for _name in ("JAVIS_RESULT_REPEAT_REFS", "JAVIS_TOOL_RESULT_SHAPING", "JAVIS_TOOL_LOOP_BUDGET_CHARS"):
    os.environ.pop(_name, None)

import engine  # noqa: E402
import mcp_client  # noqa: E402
import tool_result_reuse as reuse_mod  # noqa: E402
from tool_result_reuse import REFERENCE_MARK, RepeatResults, compact_json  # noqa: E402

fails = []


def check(name, ok, extra=None):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok or extra is None else f"  [{extra}]"))
    if not ok:
        fails.append(name)


BIG = "Báo cáo tuần: " + "dòng dữ liệu bán hàng 123.456 đồng\n" * 120     # ~4.3k chars
OTHER = "Tài liệu khác: " + "nội dung khác hẳn\n" * 120


# ───────────────────────── 1. RepeatResults on its own ─────────────────────────
r = RepeatResults(enabled=True)
conv = []
first = r.text_for("read_doc", {"path": "a.md"}, BIG)
conv.append({"role": "tool", "content": first})
r.remember("read_doc", {"path": "a.md"}, conv[-1], "content")
check("the first result goes out whole", first == BIG)

second = r.text_for("read_doc", {"path": "a.md"}, BIG)
conv.append({"role": "tool", "content": second})
r.remember("read_doc", {"path": "a.md"}, conv[-1], "content")
check("an identical repeat becomes a short reference", second.startswith(REFERENCE_MARK) and len(second) < 300,
      second[:80])
check("the reference names the tool", "read_doc" in second)
check("savings are counted", r.reused == 1 and r.saved_chars == len(BIG) - len(second), (r.reused, r.saved_chars))

check("same text from different arguments still goes out whole",
      r.text_for("read_doc", {"path": "b.md"}, BIG) == BIG)
check("argument order does not matter",
      RepeatResults.args_key({"a": 1, "b": 2}) == RepeatResults.args_key({"b": 2, "a": 1}))
check("changed data from the same call goes out whole", r.text_for("read_doc", {"path": "a.md"}, OTHER) == OTHER)
check("a small result is never replaced", RepeatResults(enabled=True).text_for("t", {}, "ok") == "ok")

# a nudge appended to the original's cell does not count as damage
conv[0]["content"] += "\n\n(nudge from the loop guard)"
check("text appended after the original keeps it whole",
      r.text_for("read_doc", {"path": "a.md"}, BIG).startswith(REFERENCE_MARK))

# the original is trimmed by the loop: no reference any more, and the newest reference gets the full text back
r2 = RepeatResults(enabled=True)
c = [{"content": None} for _ in range(3)]
for cell in c:
    cell["content"] = r2.text_for("read_doc", {"path": "a.md"}, BIG)
    r2.remember("read_doc", {"path": "a.md"}, cell, "content")
check("two repeats, two references", [x["content"].startswith(REFERENCE_MARK) for x in c] == [False, True, True])
c[0]["content"] = BIG[:1200] + "\n\n… [Javis đã rút gọn kết quả tool cũ này …]"
c[2]["content"] += "\n(nudge)"
restored = r2.after_trim()
check("a trimmed original is given back in the newest reference",
      restored == 1 and c[2]["content"] == BIG + "\n(nudge)" and c[1]["content"].startswith(REFERENCE_MARK),
      (restored, c[2]["content"][:40]))
check("the next repeat points at the restored copy",
      r2.text_for("read_doc", {"path": "a.md"}, BIG).startswith(REFERENCE_MARK))
c[2]["content"] = BIG[:1200] + "\n… [Javis đã rút gọn kết quả tool cũ này]"
check("no back and forth: older references are not refilled", r2.after_trim() == 0 and
      c[1]["content"].startswith(REFERENCE_MARK))
check("after both copies were trimmed, a repeat goes out whole again",
      r2.text_for("read_doc", {"path": "a.md"}, BIG) == BIG)

# references keep pointing at the text they repeated, not at a newer different result
r3 = RepeatResults(enabled=True)
cells = [{"content": None} for _ in range(3)]
for cell, text in zip(cells, (BIG, BIG, OTHER)):
    cell["content"] = r3.text_for("read_doc", {"path": "a.md"}, text)
    r3.remember("read_doc", {"path": "a.md"}, cell, "content")
cells[0]["content"] = "trimmed"
r3.after_trim()
check("a reference to older data is restored with that data, not with the newer result",
      cells[1]["content"] == BIG and cells[2]["content"] == OTHER)

off = RepeatResults(enabled=False)
cell = {"content": BIG}
off.remember("read_doc", {}, cell, "content")
check("switched off: a repeat goes out whole", off.text_for("read_doc", {}, BIG) == BIG)


# ───────────────────────── 2. the switches ─────────────────────────
os.environ["JAVIS_RESULT_REPEAT_REFS"] = "0"
check("JAVIS_RESULT_REPEAT_REFS=0 turns references off", RepeatResults().enabled is False)
os.environ["JAVIS_RESULT_REPEAT_REFS"] = "1"
check("JAVIS_RESULT_REPEAT_REFS=1 turns them on", RepeatResults().enabled is True)
os.environ.pop("JAVIS_RESULT_REPEAT_REFS")
with patch.object(reuse_mod, "_shaping_on", return_value=False):
    check("the Off saving level turns references off", RepeatResults().enabled is False)
    check("the Off saving level leaves JSON as it is",
          compact_json(json.dumps({"rows": list(range(400))}, indent=2), "crm_list") ==
          json.dumps({"rows": list(range(400))}, indent=2))
with patch.object(reuse_mod, "_shaping_on", return_value=True):
    check("by default references are on", RepeatResults().enabled is True)


# ───────────────────────── 3. compact JSON ─────────────────────────
data = {"orders": [{"id": i, "khach": "Nguyễn Thị Hồng", "ghi_chu": "giao buổi chiều", "tong": 125000 + i}
                   for i in range(30)]}
pretty_ascii = json.dumps(data, indent=2)                      # \u escapes, the default of json.dumps
out = compact_json(pretty_ascii, "crm_list_orders", on=True)
check("indented, escaped JSON becomes compact", len(out) < len(pretty_ascii) * 0.6, (len(out), len(pretty_ascii)))
check("same value after compacting", json.loads(out) == data)
check("Vietnamese letters come back as characters", "Nguyễn Thị Hồng" in out and "\\u" not in out)
header = "HTTP 200\n" + json.dumps(data, indent=2, ensure_ascii=False)
out = compact_json(header, "pos_report", on=True)
check("a short header before the JSON is kept", out.startswith("HTTP 200\n") and json.loads(out[9:]) == data)
jsonl = "\n".join(json.dumps(o, indent=2, ensure_ascii=False) for o in data["orders"])
out = compact_json(jsonl, "pos_rows", on=True)
check("several JSON values in a row stay several values",
      [json.loads(line) for line in out.split("\n")] == data["orders"])
pretty = json.dumps(data, indent=2, ensure_ascii=False)
for tool in ("javis_read_file", "javis_terminal", "javis_web_fetch", "javis_use_skill", "javis_edit_file"):
    check(f"{tool}: output is never re-formatted", compact_json(pretty, tool, on=True) == pretty)
mixed = pretty + "\nWarning: rate limit close"
check("JSON followed by other text is left alone", compact_json(mixed, "pos_report", on=True) == mixed)
small = json.dumps({"a": [1, 2]}, indent=2)
check("small JSON is left alone", compact_json(small, "x", on=True) == small)
already = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
check("compact JSON stays byte-identical", compact_json(already, "x", on=True) == already)
check("plain text is left alone", compact_json("x" * 5000, "x", on=True) == "x" * 5000)


# ───────────────────────── 4. through the real tool loops ─────────────────────────
SEEN = []
PLAN = []


class _Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(body)
        raw = json.dumps(PLAN.pop(0), ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


_srv = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
threading.Thread(target=_srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{_srv.server_address[1]}"
engine.OPENAI_URL = BASE + "/v1/chat/completions"
engine.ANTHROPIC_URL = BASE + "/v1/messages"

CALLS = []
VERSION = {"n": 0}


async def _read_doc(args):
    CALLS.append(args)
    if args.get("path") == "live.md":   # data that changes between two identical calls
        VERSION["n"] += 1
        return BIG + f"\nphiên bản {VERSION['n']}"
    return BIG if args.get("path") != "b.md" else OTHER


TOOLS = [{"fn": "read_doc", "server": "javis", "name": "read_doc", "description": "read a document",
          "schema": {"type": "object", "properties": {"path": {"type": "string"}}}}]
ROUTE = {"read_doc": {"call": _read_doc}}
ASK = [{"role": "user", "content": "tóm tắt tài liệu"}]


def cc_call(i, path):
    return {"choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [
        {"id": f"t{i}", "type": "function", "function": {"name": "read_doc",
                                                         "arguments": json.dumps({"path": path})}}]}}]}


def cc_text(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2}}


def tool_contents(body):
    return [m["content"] for m in body["messages"] if m.get("role") == "tool"]


async def collect(gen):
    return [ev async for ev in gen]


def run_cc(paths):
    SEEN.clear()
    CALLS.clear()
    PLAN[:] = [cc_call(i, p) for i, p in enumerate(paths)] + [cc_text("Xong.")]
    return asyncio.run(collect(engine.openai_chat_with_mcp("k", "gpt-test", ASK, "off", TOOLS, ROUTE)))


def request_chars(seen):
    return sum(len(json.dumps(b, ensure_ascii=False)) for b in seen)


evs = run_cc(["a.md", "a.md", "b.md"])
contents = tool_contents(SEEN[-1])
check("Chat Completions: the tool still runs on every call", [c["path"] for c in CALLS] == ["a.md", "a.md", "b.md"])
check("Chat Completions: the repeat reaches the model as a reference",
      contents[0] == BIG and contents[1].startswith(REFERENCE_MARK) and contents[2] == OTHER,
      [x[:30] for x in contents])
check("Chat Completions: the answer is unchanged", [e for e in evs if e["type"] == "text"][-1]["content"] == "Xong.")
with_refs = request_chars(SEEN)

os.environ["JAVIS_RESULT_REPEAT_REFS"] = "0"
run_cc(["a.md", "a.md", "b.md"])
os.environ.pop("JAVIS_RESULT_REPEAT_REFS")
without_refs = request_chars(SEEN)
check("Chat Completions: switched off, every copy goes out whole", tool_contents(SEEN[-1]) == [BIG, BIG, OTHER])
check("Chat Completions: the turn sends fewer characters with references",
      with_refs < without_refs - len(BIG), (with_refs, without_refs))

run_cc(["live.md", "live.md"])
contents = tool_contents(SEEN[-1])
check("Chat Completions: changed data between two identical calls goes out whole",
      len(contents) == 2 and contents[1].endswith("phiên bản 2") and not contents[1].startswith(REFERENCE_MARK))


def an_call(i, path):
    return {"content": [{"type": "tool_use", "id": f"u{i}", "name": "read_doc", "input": {"path": path}}],
            "stop_reason": "tool_use", "usage": {"input_tokens": 10, "output_tokens": 2}}


def an_tool_results(body):
    out = []
    for m in body["messages"]:
        if m.get("role") == "user" and isinstance(m.get("content"), list):
            for b in m["content"]:
                if b.get("type") == "tool_result":
                    c = b.get("content")
                    out.append(c if isinstance(c, str) else "".join(x.get("text", "") for x in c))
    return out


SEEN.clear()
CALLS.clear()
PLAN[:] = [an_call(0, "a.md"), an_call(1, "a.md"),
           {"content": [{"type": "text", "text": "Xong."}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 2}}]
evs = asyncio.run(collect(engine.anthropic_chat_with_mcp("k", "claude-test", ASK, "off", TOOLS, ROUTE)))
results = an_tool_results(SEEN[-1])
check("Anthropic: the tool still runs on every call", len(CALLS) == 2)
check("Anthropic: the repeat reaches the model as a reference",
      len(results) == 2 and results[0] == BIG and results[1].startswith(REFERENCE_MARK), [x[:30] for x in results])
check("Anthropic: the answer is unchanged", [e for e in evs if e["type"] == "text"][-1]["content"] == "Xong.")


# Responses API (ChatGPT plan / Codex backend): same fake as tests/python/test_responses_tool_stream.py
def done(item):
    return {"type": "response.output_item.done", "output_index": 0, "item": item}


def completed(output):
    return {"type": "response.completed", "response": {"output": output}}


class _Resp:
    status_code = 200

    def __init__(self, events):
        self.events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def aiter_lines(self):
        for event in self.events:
            yield "data: " + json.dumps(event)


class _Client:
    def __init__(self, rounds):
        self.rounds = iter(rounds)
        self.inputs = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    def stream(self, *a, **kw):
        self.inputs.append(copy.deepcopy(kw["json"]["input"]))
        return _Resp(next(self.rounds))


def rcall(i, path):
    return {"type": "function_call", "id": f"fc{i}", "call_id": f"call{i}", "name": "read_doc",
            "arguments": json.dumps({"path": path})}


async def _responses():
    client = _Client([[done(rcall(0, "a.md")), completed([])], [done(rcall(1, "a.md")), completed([])],
                      [completed([{"type": "message", "content": [{"type": "output_text", "text": "Xong."}]}])]])

    async def route(_route, name, args):
        CALLS.append(args)
        return BIG
    with patch.object(engine.httpx, "AsyncClient", return_value=client), \
            patch.object(mcp_client, "call_route", side_effect=route):
        evs = [e async for e in engine.responses_with_mcp("t", "", "gpt-test", ASK, "off", [{"fn": "read_doc"}], {})]
    return evs, client


CALLS.clear()
evs, client = asyncio.run(_responses())
outs = [i["output"] for i in client.inputs[-1] if i.get("type") == "function_call_output"]
check("Responses: the tool still runs on every call", len(CALLS) == 2)
check("Responses: the repeat reaches the model as a reference",
      len(outs) == 2 and outs[0] == BIG and outs[1].startswith(REFERENCE_MARK), [x[:30] for x in outs])
check("Responses: the answer is unchanged", evs[-1].get("content") == "Xong.", evs[-1])


# ───────────────────────── 5. the Usage page meter counts it ─────────────────────────
reuse_mod._LOG_POOL.submit(lambda: None).result(timeout=5)   # wait for the queued meter lines
import mcp_hub  # noqa: E402
stats = mcp_hub.result_size_stats(7)
rows = {(row["source"], row["tool"]) for row in stats.get("by_tool") or []}
check("repeat savings show up in the tool result meter", ("javis", "read_doc") in rows and stats["saved_chars"] > 0,
      (rows, stats.get("saved_chars")))


# ───────────────────────── 6. CLI engines (Claude Code, Codex) through the hub ─────────────────────────
import sys  # noqa: E402
import time  # noqa: E402
import turn_context as tc  # noqa: E402
import turn_lane  # noqa: E402
from tool_result_reuse import (CliRepeatResults, cli_text_for, current_turn_id, forget_current_turn,  # noqa: E402
                               lean_for_cli, turn_id_for_key)

cli = CliRepeatResults()
seq = [cli.text_for("pos_orders", {"d": "today"}, BIG) for _ in range(4)]
check("CLI: whole, reference, whole again, reference",
      [x == BIG for x in seq] == [True, False, True, False] and seq[1].startswith(REFERENCE_MARK), [x[:20] for x in seq])
check("CLI: the reference says how to get the text back", "call again with the same arguments" in seq[1])
check("CLI: changed data goes out whole", cli.text_for("pos_orders", {"d": "today"}, OTHER) == OTHER)
check("CLI: no turn, no record: whole", cli_text_for(None, "pos_orders", {}, BIG) == BIG)

with patch.object(reuse_mod, "_shaping_on", return_value=True):
    reuse_mod._switch_cache["ts"] = 0
    tok = tc.bind(tc.make("dashboard", la_chu=True))
    key = tc.issue_key()
    tid = turn_id_for_key(key)
    check("CLI: the hub and the compaction signals name the same turn", bool(tid) and tid == current_turn_id(), tid)
    a, b = lean_for_cli(BIG, "pos_orders", {}, tid), lean_for_cli(BIG, "pos_orders", {}, tid)
    check("CLI: a repeat in the turn becomes a reference", a == BIG and b.startswith(REFERENCE_MARK))
    forget_current_turn()
    check("CLI: after the engine compacts, a repeat goes out whole", lean_for_cli(BIG, "pos_orders", {}, tid) == BIG)
    pretty = json.dumps(data, indent=2)
    check("CLI: JSON from a plugin is compact on the CLI path too",
          json.loads(lean_for_cli(pretty, "crm_list", {}, tid)) == data
          and len(lean_for_cli(pretty, "crm_list", {"x": 1}, tid)) < len(pretty) * 0.6)
    tc.reset(tok)
    check("CLI: a key dies with its turn", turn_id_for_key(key) is None)

    # a warm engine keeps one lane key across turns: each turn still gets its own record
    lane = turn_lane.Lane()
    t1 = tc.bind(tc.make("dashboard", la_chu=True))
    lane.attach()
    id1 = turn_id_for_key(lane.key)
    lean_for_cli(BIG, "pos_orders", {}, id1)
    check("CLI: warm engine, first turn: repeat is a reference",
          lean_for_cli(BIG, "pos_orders", {}, id1).startswith(REFERENCE_MARK))
    lane.detach()
    tc.reset(t1)
    time.sleep(0.01)
    t2 = tc.bind(tc.make("dashboard", la_chu=True))
    lane.attach()
    id2 = turn_id_for_key(lane.key)
    check("CLI: warm engine, next turn: a fresh record, whole again",
          id2 and id2 != id1 and lean_for_cli(BIG, "pos_orders", {}, id2) == BIG, (id1, id2))
    lane.detach()
    tc.reset(t2)

    # through the real hub endpoint, as Claude Code and Codex call it
    async def _fake_discover(*a, **k):
        return ([{"fn": "pos_orders", "server": "pos", "name": "pos_orders", "description": "orders",
                  "schema": {"type": "object", "properties": {}}}],
                {"pos_orders": {"call": _read_doc_any}})

    async def _read_doc_any(args):
        return BIG

    class _Req:
        def __init__(self, turn_key, body):
            self.headers = {"authorization": f"Bearer {mcp_hub.hub_token()}", "x-javis-mode": "full"}
            if turn_key:
                self.headers["x-javis-turn"] = turn_key
            self._body = body

        async def json(self):
            return self._body

    async def _hub_call(turn_key):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "pos_orders", "arguments": {"d": "today"}}}
        resp = await mcp_hub.handle_http(_Req(turn_key, body))
        out = json.loads(resp.body.decode("utf-8"))
        return ((out.get("result") or {}).get("content") or [{}])[0].get("text", json.dumps(out))

    async def _hub_run():
        tok = tc.bind(tc.make("dashboard", la_chu=True))
        try:
            k = tc.issue_key()
            with patch.object(mcp_hub, "discover_all", _fake_discover):
                got = [await _hub_call(k) for _ in range(3)]
                anonymous = [await _hub_call(None) for _ in range(2)]
        finally:
            tc.reset(tok)
        return got, anonymous

    got, anonymous = asyncio.run(_hub_run())
    check("hub: whole, reference, whole for a CLI turn",
          [g.startswith(BIG[:40]) for g in got] == [True, False, True] and got[1].startswith(REFERENCE_MARK),
          [g[:40] for g in got])
    check("hub: a call without a turn key always gets the whole result",
          all(x.startswith(BIG[:40]) for x in anonymous), [x[:40] for x in anonymous])

    # Codex reports a compaction in its event stream: the turn's record is dropped
    import claude_cli  # noqa: E402
    tok = tc.bind(tc.make("dashboard", la_chu=True))
    k = tc.issue_key()
    tid = turn_id_for_key(k)
    lean_for_cli(BIG, "pos_orders", {}, tid)
    events = [{"type": "thread.started", "thread_id": "t-1"},
              {"type": "item.completed", "item": {"type": "context_compaction"}},
              {"type": "item.completed", "item": {"type": "agent_message", "text": "Xong."}},
              {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 1}}]
    script = "import json\n" + "\n".join(f"print(json.dumps({json.dumps(ev)}), flush=True)" for ev in events)
    codex = claude_cli.CodexCLI(cwd=os.environ["JAVIS_STATE_DIR"])
    codex.cli_path = sys.executable
    codex._build_args = lambda: [sys.executable, "-c", script]

    async def _codex_run():
        return [e async for e in codex.query("tóm tắt")]
    asyncio.run(_codex_run())
    check("Codex: a compaction in its stream drops the turn's record",
          lean_for_cli(BIG, "pos_orders", {}, tid) == BIG)
    tc.reset(tok)

# Claude Code: a wrapper (never claude_sdk_engine.py itself, which stays the qualified source byte for byte) adds a
# PreCompact hook to the SDK options, and the hook drops the turn's record
import claude_sdk_engine  # noqa: E402
import claude_result_reuse  # noqa: E402
import claude_secret_hook  # noqa: E402
if claude_sdk_engine.ClaudeSDK.pre_tool_hooks_supported():
    check("Claude Code: the wrapper installs", claude_result_reuse.install())
    claude_secret_hook.install()
    check("Claude Code: the secret hook stays the outermost wrapper",
          getattr(claude_sdk_engine.ClaudeSDK._options, "_javis_secret_hook", False))
    top = claude_sdk_engine.ClaudeSDK._options
    claude_result_reuse.install()
    check("Claude Code: installing again stacks nothing", claude_sdk_engine.ClaudeSDK._options is top)
    eng = claude_sdk_engine.ClaudeSDK(system_prompt="x", cwd=os.environ["JAVIS_STATE_DIR"], tag="chat")
    pre_compact = (getattr(eng._options(), "hooks", None) or {}).get("PreCompact") or []
    check("Claude Code: a PreCompact hook is installed",
          any(claude_result_reuse.compact_hook in (m.hooks or []) for m in pre_compact))
    with patch.object(reuse_mod, "_shaping_on", return_value=True):
        tok = tc.bind(tc.make("dashboard", la_chu=True))
        tid = turn_id_for_key(tc.issue_key())
        lean_for_cli(BIG, "pos_orders", {}, tid)
        out = asyncio.run(claude_result_reuse.compact_hook({"hook_event_name": "PreCompact"}, None, None))
        check("Claude Code: the hook decides nothing and drops the turn's record",
              out == {} and lean_for_cli(BIG, "pos_orders", {}, tid) == BIG)
        tc.reset(tok)
else:
    print("skip  SDK without hooks")


print()
if fails:
    print(f"{len(fails)} FAIL")
    raise SystemExit(1)
print("all ok")
