"""Javis Gate: model and effort from the outside AI's command, and a notice when work it sent finishes unread.

    python tests/run.py javis_gate_model_notice -v      (no network)

Owner, 14/11/2026: "ChatGPT should be able to change Javis's model and effort from inside its command", and "when Javis
finishes a long job, tell ChatGPT so it wakes up and reads the result". ChatGPT cannot be woken from outside, so the
second half becomes: ChatGPT waits longer in the same reply, the owner's phone rings when work it sent finishes while
it is not waiting, and `javis_chat_updates` hands every unread result over in any ChatGPT chat.

Runs the real web chat loop (`main._chat_socket`) with a fake OpenRouter, like test_javis_gate_chat.py, and locks:
1. `chon_model` / `chuan_effort`: exact "<provider>/<model>", a unique model or card, "default"; never a guess
   between two cards; effort names from other vendors and in Vietnamese.
2. `javis_chat_send` with model + effort: the chat is pinned to that model (the turn really runs on it), the effort
   reaches the engine for THAT message only, nothing in settings changes.
3. A bad model, a bad effort, or a change while the chat is answering: refused before anything is sent.
4. Work the outside AI did not read rings the bell once (with the answer and what to say to ChatGPT); work it read
   rings nothing, and the long-turn bell does not ring a second time for it.
5. `javis_chat_updates`: unread results across chats, per AI, then nothing; running work says how long.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
os.environ["JAVIS_API_STREAM_TOOLS"] = "0"
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-gate-model-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import main  # noqa: E402
import engine  # noqa: E402
import chat_bridge as CB  # noqa: E402
import mcp_hub  # noqa: E402
from chat_runtime import ChatRuntime  # noqa: E402

_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info})"))
    if not cond:
        _fails.append(name)


class _Resp:
    def __init__(self, data):
        self.status_code, self._data, self.text, self.headers = 200, data, json.dumps(data), {}

    def json(self):
        return self._data


CHAM = {"s": 0.02}
GOI = []   # every request the fake provider got: {"model", "reasoning", "last"}


class _FakeClient:
    """Like OpenRouter: answers "ĐÃ LÀM: <last line of the owner's message>" and records model and reasoning."""

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        body = json or {}
        msgs = body.get("messages") or []
        cuoi = next((m.get("content") for m in reversed(msgs) if m.get("role") == "user"), "")
        dong = str(cuoi or "").strip().splitlines()[-1] if str(cuoi or "").strip() else ""
        GOI.append({"model": body.get("model"), "reasoning": body.get("reasoning"), "last": dong})
        await asyncio.sleep(CHAM["s"])
        return _Resp({"choices": [{"message": {"content": "ĐÃ LÀM: " + dong[:120]}}],
                      "usage": {"prompt_tokens": 1, "completion_tokens": 1}})


RUNTIME = ChatRuntime()
main._CHAT_RUNTIME = RUNTIME
main.cfgmod.gate_active = lambda: False
main._chat_provider = lambda _cfg: ("openrouter", "api", "test-key", "test-model")
main._reasoning_level = lambda _cfg: "off"
main.log_conversation = lambda brain, u, j: None
main.usage_store.record = lambda *a, **k: None
engine.httpx.AsyncClient = _FakeClient


async def _none(*a, **k):
    return None


async def _false(*a, **k):
    return False
main._schedule_cancel_action = _none
main.compaction.maybe_compact = _false


async def _hoc(*a, **k):
    return None
main.learn_feature.enqueue = _hoc

CHUONG = []   # what reached the bell


async def _chuong(owner_chat, text, **kw):
    CHUONG.append({"chat": owner_chat, "text": text, **kw})
    return {"id": f"n{len(CHUONG)}"}
main._bo_vao_hom_thu = _chuong

# OpenRouter is a connected card with two models, so the Gate can pin one and the turn can really run on it.
main.cfgmod.update_settings({"model": {"openrouter_key": "test-key",
                                       "catalog": {"openrouter": ["test-model", "test-model-2"]}}})
CAI_DAT_TRUOC = json.dumps(main.cfgmod.read_settings().get("model", {}), sort_keys=True)

BRAIN = main._brain_key(str(Path(tempfile.mkdtemp(prefix="brain-gate-model-")).resolve()))
ss = main.get_store()
WEB = ss.create_session(brain=BRAIN, engine="test", model="test", title="Viết Web bán nước mắm")
WEB2 = ss.create_session(brain=BRAIN, engine="test", model="test", title="Kế hoạch Tết")


def chay(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


asyncio.set_event_loop(asyncio.new_event_loop())
GATE = {"source": "ChatGPT"}


def goi(name, args, mode="full", gate=GATE):
    res = chay(mcp_hub._handle_one({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                    "params": {"name": name, "arguments": args}}, mode, gate=gate))
    txt = res["result"]["content"][0]["text"]
    return txt, res["result"]["isError"]


def ten_tool(mode, gate):
    res = chay(mcp_hub._handle_one({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, mode, gate=gate))
    return {t["name"]: t for t in res["result"]["tools"]}


def cho_xong(sid, toi_da=10.0):
    async def _cho():
        for _ in range(int(toi_da / 0.05)):
            if not RUNTIME.get_job(sid):
                return True
            await asyncio.sleep(0.05)
        return False
    return chay(_cho())


def ngu(s):
    chay(asyncio.sleep(s))


# ============================================================
# 1. Choosing a model and an effort from the AI's words
# ============================================================
DS = [{"provider": "anthropic-cli", "name": "Claude Code", "models": ["claude-opus-5-5", "claude-sonnet-5-5"]},
      {"provider": "anthropic-api", "name": "Anthropic (API)", "models": ["claude-opus-5-5"]},
      {"provider": "openai-oauth", "name": "ChatGPT (Codex)", "models": ["gpt-5.5", "gpt-5.5-codex"]},
      {"provider": "openrouter", "name": "OpenRouter", "models": ["openai/gpt-4o", "anthropic/claude-opus-5-5"]},
      {"provider": "openai", "name": "OpenAI (ChatGPT API)", "models": ["gpt-4o"]}]


def chon(q):
    r = CB.chon_model(q, DS)
    return (r["provider"], r["model"]) if r.get("ok") else ("ERR", r.get("error", ""))


check("'<provider>/<model>' exactly", chon("anthropic-cli/claude-opus-5-5") == ("anthropic-cli", "claude-opus-5-5"))
check("an OpenRouter id that itself holds a '/'", chon("openrouter/openai/gpt-4o") == ("openrouter", "openai/gpt-4o"))
check("'openai/gpt-4o' is the OpenAI card's gpt-4o", chon("openai/gpt-4o") == ("openai", "gpt-4o"))
check("a spoken name finds the one model: 'Sonnet 5.5'", chon("Sonnet 5.5") == ("anthropic-cli", "claude-sonnet-5-5"))
check("'gpt 5.5' is gpt-5.5, not gpt-5.5-codex", chon("gpt 5.5") == ("openai-oauth", "gpt-5.5"))
check("a card alone means its default model", chon("anthropic-cli") == ("anthropic-cli", ""))
check("'default' unpins (follow the main model)", chon("default") == ("", "") and chon("Mặc định") == ("", ""))
r = chon("claude-opus-5-5")
check("the same id on a plan card and an API card: no guess, both offered",
      r[0] == "ERR" and "anthropic-cli/claude-opus-5-5" in r[1] and "anthropic-api/claude-opus-5-5" in r[1], r)
r = chon("llama")
check("nothing matches: says so and points to javis_chat_models", r[0] == "ERR" and "javis_chat_models" in r[1], r)
check("effort: Javis's own levels pass through", CB.chuan_effort("xhigh") == "xhigh" and CB.chuan_effort("") == "")
check("effort: other vendors' names map ('max' is Javis's 'ultra')",
      CB.chuan_effort("max") == "ultra" and CB.chuan_effort("none") == "off" and CB.chuan_effort("High") == "high")
check("effort: Vietnamese words map", CB.chuan_effort("cao") == "high" and CB.chuan_effort("tối đa") == "ultra")
check("effort: anything else is refused", CB.chuan_effort("turbo") is None)

# ============================================================
# 2. The tools on the Gate
# ============================================================
full = ten_tool("full", GATE)
check("Full access lists javis_chat_models and javis_chat_updates",
      "javis_chat_models" in full and "javis_chat_updates" in full)
sug = ten_tool("suggest", GATE)
check("Read only still lists both (they only read)", "javis_chat_models" in sug and "javis_chat_updates" in sug)
props = full["javis_chat_send"]["inputSchema"]["properties"]
check("javis_chat_send takes model and effort, effort on Javis's ladder",
      "model" in props and props["effort"].get("enum") == list(engine.REASONING_LEVELS), props.get("effort"))
check("javis_chat_send keeps id and message as the only required fields",
      full["javis_chat_send"]["inputSchema"]["required"] == ["id", "message"])
check("the tools never show on Javis's own engines", "javis_chat_models" not in ten_tool("full", None))

txt, loi = goi("javis_chat_models", {"id": WEB})
d = json.loads(txt) if not loi else {}
orr = next((p for p in d.get("providers", []) if p["provider"] == "openrouter"), {})
check("javis_chat_models: connected cards with their models", not loi and "test-model-2" in orr.get("models", []), txt[:300])
check("javis_chat_models: the effort ladder", d.get("efforts") == list(engine.REASONING_LEVELS))
check("javis_chat_models with id: the chat's current model and effort",
      (d.get("chat") or {}).get("id") == WEB and "effort" in (d.get("chat") or {}), d.get("chat"))
txt, loi = goi("javis_chat_models", {"query": "model-2"})
d = json.loads(txt) if not loi else {}
check("javis_chat_models query filters the models",
      [p["models"] for p in d.get("providers", []) if p["provider"] == "openrouter"] == [["test-model-2"]], txt[:300])

# ============================================================
# 3. Sending with a model and an effort
# ============================================================
GOI.clear()
txt, loi = goi("javis_chat_send", {"id": WEB, "message": "Viết lại trang chủ.", "model": "openrouter/test-model-2",
                                   "effort": "high", "wait_seconds": 10})
kq = json.loads(txt) if not loi else {}
check("send with model + effort: Javis answers", not loi and (kq.get("result") or {}).get("status") == "done", txt[:300])
row = ss.get_session(WEB)
check("the chat is pinned to that model, as the model bar does",
      row.get("pinned_provider") == "openrouter" and row.get("pinned_model") == "test-model-2", row)
luot = [g for g in GOI if "trang chủ" in g["last"]]
check("the turn really ran on that model", luot and luot[0]["model"] == "test-model-2", GOI)
check("the effort reached the engine for that message", luot and luot[0]["reasoning"] == {"effort": "high"}, luot)
m = kq.get("model") or {}
check("the reply says which model and effort, and that the effort was for this message",
      m.get("provider") == "openrouter" and m.get("model") == "test-model-2" and m.get("effort") == "high"
      and m.get("effort_for") == "this message only", m)
check("nothing in the settings changed (the effort chip and the main model stay)",
      json.dumps(main.cfgmod.read_settings().get("model", {}), sort_keys=True) == CAI_DAT_TRUOC)

GOI.clear()
txt, loi = goi("javis_chat_send", {"id": WEB, "message": "Thêm chân trang.", "wait_seconds": 10})
luot = [g for g in GOI if "chân trang" in g["last"]]
check("next message without effort: back to the chat's own level", luot and luot[0]["reasoning"] is None, luot)
check("next message without model: still on the pinned model", luot and luot[0]["model"] == "test-model-2", luot)
check("a send without model or effort does not add a 'model' block", "\"model\"" not in txt.split("\"result\"")[0], txt)

so_tin = len(ss.get_messages(WEB))
txt, loi = goi("javis_chat_send", {"id": WEB, "message": "x", "model": "khong-co-model-nay"})
check("unknown model: refused, nothing sent", loi and "javis_chat_models" in txt and len(ss.get_messages(WEB)) == so_tin, txt)
txt, loi = goi("javis_chat_send", {"id": WEB, "message": "x", "effort": "turbo"})
check("unknown effort: refused, nothing sent", loi and "effort must be one of" in txt
      and len(ss.get_messages(WEB)) == so_tin, txt)
check("the refused model did not touch the pin", ss.get_session(WEB).get("pinned_model") == "test-model-2")

CHAM["s"] = 0.6


async def _ban():
    r1 = await CB.gui(WEB, "Việc dài.", "ChatGPT")
    await asyncio.sleep(0.1)
    r2 = await CB.gui(WEB, "Đổi model giữa chừng.", "ChatGPT", model="openrouter/test-model", effort="low")
    r3 = await CB.gui(WEB, "Gõ thêm thường.", "ChatGPT")
    return r1, r2, r3
r1, r2, r3 = chay(_ban())
check("model or effort while the chat answers: refused with the reason", not r2.get("ok")
      and "between turns" in r2.get("error", ""), r2)
check("the pin did not change mid-turn", ss.get_session(WEB).get("pinned_model") == "test-model-2")
check("a plain message while it answers is still taken", r3.get("ok") and r3.get("mode") == "queued", r3)
cho_xong(WEB)
ngu(1.5)
cho_xong(WEB)
CHAM["s"] = 0.02
chay(CB.ket_qua(WEB, r1["after_id"], 10))

txt, loi = goi("javis_chat_send", {"id": WEB, "message": "Quay về model chính.", "model": "default", "wait_seconds": 10})
row = ss.get_session(WEB)
check("model 'default' unpins the chat", not loi and not row.get("pinned_provider"), (txt[:200], row.get("pinned_provider")))

# ============================================================
# 4. Work the outside AI stopped waiting for rings the owner, once
# ============================================================
# Longer than javis_chat_result's one-second second look, as the real 60 s is, so a read result is never rung.
CB.CHO_DOC_S = 2.0
CHUONG.clear()
txt, loi = goi("javis_chat_send", {"id": WEB2, "message": "Lập kế hoạch quảng cáo Tết.", "wait_seconds": 0})
gui1 = json.loads(txt)
check("send without waiting: started", not loi and gui1.get("mode") == "started", txt[:200])
check("while it runs the chat counts as holding unread Gate work", CB.co_viec(WEB2))
cho_xong(WEB2)
ngu(2.6)
check("ChatGPT never read it: the bell rang once", len(CHUONG) == 1, CHUONG)
c = CHUONG[0] if CHUONG else {}
check("the bell is the chat's, with the answer, and asks for a push", c.get("chat") == f"web:{WEB2}"
      and "quảng cáo Tết" in c.get("text", "") and c.get("push_if_away") is True, c)
dong_dau = c.get("text", "").splitlines()[0] if c.get("text") else ""
check("its first line (the phone's title) names the AI and the chat",
      "ChatGPT" in dong_dau and "Kế hoạch Tết" in dong_dau, dong_dau)
check("it tells the owner what to say to ChatGPT", "xem kết quả Javis" in c.get("text", ""), c.get("text"))
check("one notice per task (dedup key of the task)", c.get("dedup") == f"gate:{WEB2}:{gui1['after_id']}", c.get("dedup"))
ngu(0.6)
check("no second ring later", len(CHUONG) == 1, len(CHUONG))

txt, loi = goi("javis_chat_updates", {}, gate={"source": "Claude"})
check("Claude does not see ChatGPT's tasks", not loi and json.loads(txt)["items"] == [], txt[:200])
txt, loi = goi("javis_chat_updates", {})
d = json.loads(txt) if not loi else {}
it = (d.get("items") or [{}])[0]
check("javis_chat_updates: the unread result, with Javis's answer", it.get("id") == WEB2 and it.get("status") == "done"
      and "quảng cáo Tết" in it.get("answer", ""), txt[:300])
txt, loi = goi("javis_chat_updates", {})
check("read once: the next call has nothing new", not loi and json.loads(txt)["items"] == [], txt[:200])
check("and the chat holds no unread Gate work", not CB.co_viec(WEB2))

CHUONG.clear()
txt, loi = goi("javis_chat_send", {"id": WEB2, "message": "Thêm kênh Zalo.", "wait_seconds": 10})
check("ChatGPT waited and read the answer itself", not loi and (json.loads(txt).get("result") or {}).get("status") == "done")
ngu(2.6)
check("so no bell rang", CHUONG == [], CHUONG)

CHUONG.clear()
CB._them_viec(ss.get_session(WEB2), 10 ** 9, "ChatGPT")
da = chay(main._bao_luot_dai_xong(WEB2, BRAIN, "t1", "x", "Một câu trả lời dài.", 99999))
check("a long Gate turn nobody read: the long-turn bell steps aside for the Gate notice", da is False and CHUONG == [])
CB._da_doc(WEB2, 0)
da = chay(main._bao_luot_dai_xong(WEB2, BRAIN, "t2", "x", "Một câu trả lời dài.", 99999))
check("once read, a long turn rings as before", da is True and len(CHUONG) == 1, CHUONG)

# ============================================================
# 5. Running work: how long, and the advice to keep waiting
# ============================================================
CHAM["s"] = 1.2
CHUONG.clear()


async def _dang_lam():
    r = await CB.gui(WEB2, "Việc lâu.", "ChatGPT")
    await asyncio.sleep(0.3)
    kq = await CB.ket_qua(WEB2, r["after_id"], 0)
    cap = CB.cap_nhat("ChatGPT")
    return r, kq, cap
r, kq, cap = chay(_dang_lam())
check("still running: status running with working_for_s", kq.get("status") == "running"
      and isinstance(kq.get("working_for_s"), int), kq)
check("the hint says keep waiting in this reply, then javis_chat_updates",
      "keep waiting" in kq.get("hint", "") and "javis_chat_updates" in kq.get("hint", ""), kq.get("hint"))
check("javis_chat_updates lists running work without marking it read",
      cap["items"] and cap["items"][0]["status"] == "running" and CB.co_viec(WEB2), cap)
cho_xong(WEB2)
CHAM["s"] = 0.02
kq = chay(CB.ket_qua(WEB2, r["after_id"], 5))
check("reading the result marks it read: no bell", kq.get("status") == "done" and not CB.co_viec(WEB2))
ngu(2.0)
check("and nothing rang", CHUONG == [], CHUONG)
desc = full["javis_chat_result"]["description"]
check("javis_chat_result tells the AI to keep waiting, then javis_chat_updates",
      "keep waiting" in desc and "javis_chat_updates" in desc, desc)
for f in ("chat_bridge.py",):
    chu = (SERVER / f).read_text(encoding="utf-8")
    check(f"{f}: no em dash or en dash", chr(0x2014) not in chu and chr(0x2013) not in chu)

print()
print("ALL PASS" if not _fails else f"{len(_fails)} FAIL: {_fails}")
raise SystemExit(1 if _fails else 0)
