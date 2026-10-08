"""Resonance A1, review tích hợp: đường THẬT tới engine và tool, không gọi model hay mạng thật.

    python tests/run.py resonance_a1_transport -v

1. P1-1, prompt cuối engine nhận: chạy trọn `websocket_endpoint` (lượt chat thật của dashboard) với engine API.
   HTTP của nhà cung cấp được giả lập ở `engine.httpx.AsyncClient`, nên vòng tool THẬT (`engine._cc_tool_loop`,
   `mcp_client.call_route`, hub và plugin) chạy nguyên. Bắt system prompt và danh sách tool đúng như gửi đi:
   phiên trợ lý bật, phiên trợ lý tắt, chat thường.
2. Đường tool engine API: "model" giả gọi javis_goal; hai lượt của hai trợ lý chạy xen nhau. Mỗi mục tiêu phải gắn
   đúng trợ lý, đúng phiên, đúng tin.
3. Đường tool Claude SDK: server MCP trong tiến trình THẬT (`ClaudeSDK._plugins_server`) gọi qua bộ điều phối
   `CallToolRequest` của chính server đó, trong hai lượt chạy xen nhau.
4. P1-2, file trợ lý mất mà không có lượt chat: nhịp nền (`resonance.tick` với deps thật của main) không gọi engine,
   không đăng, không chốt đạt; sổ chuyển missing; đổi tên tay hay đặt file lại vẫn bị chặn tới khi chủ xác nhận.
   `/goal-requests` cũng bị chặn.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-a1x-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import main  # noqa: E402
import engine  # noqa: E402
import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402
import turn_context  # noqa: E402
import _resonance_agent as RA  # noqa: E402
from chat_runtime import ChatRuntime  # noqa: E402
from fastapi import WebSocketDisconnect  # noqa: E402

_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info})"))
    if not cond:
        _fails.append(name)


BRAIN = main._brain_key(str(Path(tempfile.mkdtemp(prefix="brain-a1x-")).resolve()))
OWNER = RS.Principal("owner", "owner", BRAIN)
store = main._resonance_store()
A = RA.enable(store, BRAIN, "viet-bai")
B = RA.enable(store, BRAIN, "kiem-tra")
C = RA.enable(store, BRAIN, "tat-san")
C = RA.disable(store, BRAIN, "tat-san")
ss = main.get_store()
USER = "Em lo giúp anh bản hướng dẫn nhận hàng Docs/hd.md, sửa tới khi anh thấy dùng được."
PROPOSAL = {"op": "create", "understanding": "Bản hướng dẫn nhận hàng",
            "relevant_quote": "Em lo giúp anh bản hướng dẫn nhận hàng",
            "criteria": [{"description": "Có mục Lỗi hay gặp", "evaluator": "artifact_contract",
                          "params": {"path": "Docs/hd.md", "must_contain": ["Lỗi hay gặp"]}}],
            "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"}, "stage": "delivery",
            "mode": "achieve"}

# ───────────── engine API: HTTP của nhà cung cấp giả, mọi thứ còn lại thật ─────────────
SEEN = []          # mỗi request gửi đi: (system prompt, tên tool, đã có kết quả tool chưa)


class _Resp:
    def __init__(self, data):
        self.status_code, self._data, self.text, self.headers = 200, data, json.dumps(data), {}

    def json(self):
        return self._data


class _FakeClient:
    """Thay httpx.AsyncClient trong engine: trả như OpenRouter. Lượt đầu "model" gọi javis_goal nếu tool có trong
    danh sách, lượt sau trả chữ. Ngủ một nhịp để hai lượt chat chạy xen nhau."""

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        msgs = (json or {}).get("messages") or []
        names = [((t.get("function") or {}).get("name")) for t in (json or {}).get("tools") or []]
        has_result = any(m.get("role") == "tool" for m in msgs)
        SEEN.append({"system": next((m.get("content") for m in msgs if m.get("role") == "system"), ""),
                     "tools": names, "has_result": has_result, "user": msgs[-1].get("content") if msgs else ""})
        await asyncio.sleep(0.02)
        n_results = sum(1 for m in msgs if m.get("role") == "tool")
        found = any("javis_goal" in str(m.get("content") or "") for m in msgs if m.get("role") == "tool")

        def _call(fn, args):
            return _Resp({"choices": [{"message": {"content": "", "tool_calls": [{
                "id": f"call_{n_results}", "type": "function",
                "function": {"name": fn, "arguments": __import__("json").dumps(args)}}]}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
        # Như model theo đúng dòng gợi ý: engine API nạp lười chỉ thấy tool lõi, nên TÌM javis_goal rồi CHẠY qua
        # javis_run_tool. Tool có sẵn trong danh sách thì gọi thẳng.
        if "javis_goal" in names and not has_result:
            return _call("javis_goal", PROPOSAL)
        if "javis_search_tools" in names and n_results == 0:
            return _call("javis_search_tools", {"query": "javis_goal mục tiêu"})
        if "javis_run_tool" in names and n_results == 1 and found:
            return _call("javis_run_tool", {"name": "javis_goal", "args": PROPOSAL})
        tool_out = next((m.get("content") for m in reversed(msgs) if m.get("role") == "tool"), "")
        return _Resp({"choices": [{"message": {"content": "xong. " + str(tool_out)[:200]}}],
                      "usage": {"prompt_tokens": 1, "completion_tokens": 1}})


class _Ws:
    cookies = {}

    def __init__(self, payload):
        self._payload = json.dumps(payload)
        self.sent = []

    async def accept(self):
        pass

    async def close(self, code=None):
        pass

    async def send_text(self, value):
        self.sent.append(json.loads(value))

    async def receive_text(self):
        if self._payload is not None:
            v, self._payload = self._payload, None
            return v
        raise WebSocketDisconnect()


RUNTIME = ChatRuntime()
main._CHAT_RUNTIME = RUNTIME
main.cfgmod.gate_active = lambda: False
main._chat_provider = lambda _cfg: ("openrouter", "api", "test-key", "test-model")
main._reasoning_level = lambda _cfg: "off"
main.log_conversation = lambda *a, **k: None
main.usage_store.record = lambda *a, **k: None
engine.httpx.AsyncClient = _FakeClient


async def _none(*a, **k):
    return None


async def _false(*a, **k):
    return False
main._schedule_cancel_action = _none
main.compaction.maybe_compact = _false
main.learn_feature.enqueue = _none


async def _turn(sid, text):
    await main.websocket_endpoint(_Ws({"message": text, "brain": BRAIN, "session_id": sid}))
    end = time.monotonic() + 20
    while time.monotonic() < end:
        if RUNTIME.get_job(sid) is None:
            return
        await asyncio.sleep(0.01)


def turns(*pairs):
    async def _all():
        await asyncio.gather(*[_turn(s, t) for s, t in pairs])
    asyncio.run(_all())


def sess(channel):
    return ss.create_session(brain=BRAIN, engine="test", model="test", channel=channel)


SA, SB, SC, SN = sess("agent:viet-bai"), sess("agent:kiem-tra"), sess("agent:tat-san"), sess("web")
turns((SA, USER), (SB, USER))
by_sys = {}
for s in SEEN:
    by_sys.setdefault("viet" if "viet-bai" in s["system"] else "kiem" if "kiem-tra" in s["system"] else "?", []).append(s)
gA = [g for g in store.list_open(OWNER, session_id=SA)]
gB = [g for g in store.list_open(OWNER, session_id=SB)]
uA = [m for m in ss.get_messages(SA) if m["role"] == "user"]
uB = [m for m in ss.get_messages(SB) if m["role"] == "user"]
first = [s for s in SEEN if not s["has_result"]]
check("1 phiên trợ lý bật: prompt engine nhận có dòng gợi ý javis_goal và câu BA lối, không còn 'chỉ hai lối'",
      len(first) >= 2 and all("javis_goal op=create" in s["system"] and "Ba lối đúng" in s["system"]
                               and "Chỉ hai lối đúng" not in s["system"] for s in first),
      [s["system"][:80] for s in first])
searched = [x for x in SEEN if x["has_result"] and "javis_goal" in x["user"] + str(x)]
check("1 phiên trợ lý bật: engine API (nạp lười) tìm thấy javis_goal qua javis_search_tools",
      all("javis_search_tools" in s["tools"] and "javis_run_tool" in s["tools"] for s in first) and searched)
check("2 engine API, hai lượt xen nhau: mỗi phiên đúng một mục tiêu, gắn đúng trợ lý và đúng tin",
      len(gA) == 1 and len(gB) == 1 and gA[0].agent_key == A["agent_key"] and gB[0].agent_key == B["agent_key"]
      and gA[0].request_ref == R.message_ref(SA, uA[-1]["id"]) and gB[0].request_ref == R.message_ref(SB, uB[-1]["id"]),
      ([g.agent_key for g in gA], [g.agent_key for g in gB]))
check("2 tool trả về đúng mục tiêu cho đúng lượt (không lẫn kết quả)",
      any(gA[0].id in (m.get("content") or "") for m in ss.get_messages(SA))
      and not any(gA[0].id in (m.get("content") or "") for m in ss.get_messages(SB)) if gA and gB else False)

SEEN.clear()
turns((SC, USER))
check("1 phiên trợ lý TẮT: prompt như trước A1 (chỉ hai lối, không gợi ý), danh sách tool đầu không có javis_goal, không mục tiêu",
      SEEN and "Chỉ hai lối đúng" in SEEN[0]["system"] and "javis_goal op=create" not in SEEN[0]["system"]
      and "javis_goal" not in SEEN[0]["tools"] and not store.list_open(OWNER, session_id=SC),
      SEEN[0]["system"][:80] if SEEN else None)
SEEN.clear()
turns((SN, USER))
check("1 chat thường: không có dòng gợi ý, danh sách tool đầu không có javis_goal, không lập mục tiêu",
      SEEN and "javis_goal op=create" not in SEEN[0]["system"] and "javis_goal" not in SEEN[0]["tools"]
      and not store.list_open(OWNER, session_id=SN))

_sc = [m.get("content") or "" for m in ss.get_messages(SC) if m["role"] == "assistant"]
check("1 phiên trợ lý TẮT: nếu model vẫn tìm và gọi javis_goal (danh sách tool của hub là đệm, chỉ gợi ý) thì "
      "tool trả ERROR agent_off, không ghi gì", not store.list_open(OWNER, session_id=SC)
      and all("ERROR" in c and "agent_off" in c for c in _sc if "javis_goal" in c or "Cộng hưởng" in c))

# Engine gói thuê bao (Claude Code, Codex) dựng prompt ở _subscription_system_prompt: phiên trợ lý phải về đúng
# _legacy_system_prompt, mà nhánh trợ lý của nó là _agent_chat_prompt (đã kiểm ở trên qua engine API).
import ast  # noqa: E402
_src = (SERVER / "main.py").read_text(encoding="utf-8")
_fns = {n.name: ast.get_source_segment(_src, n) for n in ast.walk(ast.parse(_src))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in ("_legacy_system_prompt",
                                                                                  "_subscription_system_prompt")}
check("1 mọi nhánh engine của phiên trợ lý dùng _agent_chat_prompt (gói thuê bao qua _legacy_system_prompt)",
      "_agent_chat_prompt(brain, _persona[1])" in _fns.get("_legacy_system_prompt", "")
      and "if _persona:\n                    return _legacy_system_prompt(), None" in _fns.get("_subscription_system_prompt", ""))

# ───────────── Claude SDK: server MCP trong tiến trình, gọi qua bộ điều phối của chính nó ─────────────
import claude_sdk_engine  # noqa: E402
from mcp.types import CallToolRequest, CallToolRequestParams  # noqa: E402

SDK = {}


async def _sdk_turn(agent, slug, sid, mid):
    with RA.turn(agent, sid, mid, USER, BRAIN, slug=slug):
        e = claude_sdk_engine.ClaudeSDK(cwd=BRAIN)
        e.javis_vault = BRAIN
        cfg = e._plugins_server()
        server = cfg["instance"]
        await asyncio.sleep(0.01)
        req = CallToolRequest(method="tools/call", params=CallToolRequestParams(name="javis_goal", arguments=PROPOSAL))
        res = await server.request_handlers[CallToolRequest](req)
        SDK[slug] = res


async def _sdk_both():
    await asyncio.gather(_sdk_turn(A, "viet-bai", "kA", 7), _sdk_turn(B, "kiem-tra", "kB", 7))


asyncio.run(_sdk_both())
gkA = store.find_by_key(OWNER, R.message_ref("kA", 7))
gkB = store.find_by_key(OWNER, R.message_ref("kB", 7))
check("3 Claude SDK, hai lượt xen nhau qua server plugin thật: mỗi mục tiêu đúng trợ lý, đúng phiên, đúng tin",
      gkA is not None and gkB is not None and gkA.agent_key == A["agent_key"] and gkB.agent_key == B["agent_key"])


async def _sdk_plain():
    tok = turn_context.bind(turn_context.make("dashboard", chat_id="plain", la_chu=True, session_id="plain",
                                              message_id=3))
    try:
        e = claude_sdk_engine.ClaudeSDK(cwd=BRAIN)
        e.javis_vault = BRAIN
        cfg = e._plugins_server()
        names = [t.name for t in (await cfg["instance"].request_handlers[__import__("mcp.types").types.ListToolsRequest](
            __import__("mcp.types").types.ListToolsRequest(method="tools/list"))).root.tools]
        return names
    finally:
        turn_context.reset(tok)


check("3 Claude SDK, lượt chat thường: server plugin không mang javis_goal", "javis_goal" not in asyncio.run(_sdk_plain()))

# ───────────── P1-2: file trợ lý mất, không có lượt chat ─────────────
calls = {"n": 0}


class _Eng:
    max_wall_s = None

    def is_available(self):
        return True

    async def query(self, prompt):
        calls["n"] += 1
        yield {"type": "final", "content": "# Hướng dẫn\n\n## Lỗi hay gặp\n\n- Thiếu phiếu\n"}


main._resonance_engine = lambda s, t="resonance": (_Eng(), {"provider": "fake", "text_only": True})
deliv = Path(BRAIN) / "Docs" / "hd.md"
deliv.unlink(missing_ok=True)
gm = gB[0] if gB else gkB
store.finish_handoff(OWNER, gm.id, gm.revision, gm.request_ref, None)   # nhả lịch đã giữ trong lượt
fB = Path(BRAIN) / "agents" / "kiem-tra.md"
fB.unlink()


def tick():
    with __import__("sqlite3").connect(str(store.path)) as c:      # đưa lịch của mục tiêu này tới hạn ngay
        c.execute("UPDATE wakeups SET due_at=? WHERE goal_id!=?", (9e18, gm.id))   # chỉ mục tiêu đang xét
        c.execute("UPDATE wakeups SET due_at=? WHERE goal_id=?", (time.time() - 1, gm.id))
    asyncio.run(R.tick(store, time.time(), main._resonance_deps, limit=20))


tick()
check("4 file trợ lý bị xoá tay, không có lượt chat: nhịp nền KHÔNG gọi engine, không đăng, không chốt đạt",
      calls["n"] == 0 and not deliv.exists() and store.get(OWNER, gm.id).status == "active")
check("4 sổ chuyển missing, mục tiêu chặn agent_missing",
      store.agent_by_key(BRAIN, B["agent_key"])["status"] == "missing"
      and store.run_state(OWNER, gm.id)["block_reason"] == "agent_missing")
fB.with_name("kiem-tra-moi.md").write_text("---\nname: Kiểm tra\n---\nđổi tên tay\n", encoding="utf-8")
tick()
check("4 đổi tên tay (file mang tên khác): vẫn chặn, không gọi engine", calls["n"] == 0)
fB.with_name("kiem-tra-moi.md").rename(fB)
tick()
check("4 đặt file lại đúng tên: vẫn chặn tới khi chủ dự án xác nhận", calls["n"] == 0
      and store.agent_by_key(BRAIN, B["agent_key"])["status"] == "missing")
mid_r = ss.append_message(SB, "user", USER)
from fastapi.testclient import TestClient  # noqa: E402
r = TestClient(main.app, base_url="http://127.0.0.1:8080").post(
    "/goal-requests", params={"brain": BRAIN}, json={"message_ref": R.message_ref(SB, mid_r)})
check("4 /goal-requests trên phiên của trợ lý đang missing: 403", r.status_code == 403, r.status_code)
store.agent_confirm(OWNER, B["agent_key"], True)
store.wake_agent_goals(BRAIN, B["agent_key"])
tick()
check("4 chủ xác nhận đúng trợ lý cũ: mục tiêu chạy lại theo quyền hiện tại", calls["n"] == 1 and deliv.exists())

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
