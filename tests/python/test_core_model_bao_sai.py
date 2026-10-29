"""Javis Core chọn model và bớt thông báo đăng nhập báo sai (0.402.0; chủ repo 29/10/2026: "Jarvis Core đang không có cài
đặt được model", "nhiều thông báo đặt là sign in nhưng mà nó vẫn hiện thông báo").

    python tests/run.py core_model_bao_sai

Spec: docs/dev/2026-10-javis-core-chi-huy-thong-bao.md mục 1 và 2. Không mạng, không model.
- Mọi chat Javis Core theo ghim của Core (`model.core_provider/core_model`), không ghim thì theo model chính, ghim riêng
  của một chat bị bỏ qua; chọn model trên thanh model của chat Core là ghim cho cả Core; "Theo model chính" gỡ ghim;
  chat Core không bị đóng dấu model ở lượt đầu; meta trả ghim của Core.
- Đèn não chỉ dò lỗi đăng nhập trong lượt lỗi hoặc kết quả một dòng ngắn; cờ "đã báo" còn sau khi khởi động lại.
- Kiểm tra sau khởi động không tính kết nối đang tải lần đầu là hỏng.
- Bàn sự cố: sự cố đang "cần bạn" gom các lần hỏng sau của cùng việc, không báo lại.
- Zalo bị giành phiên: mốc báo ghi xuống kho.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-core-model-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{str(extra)[:300]}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


import config as cfgmod  # noqa: E402
import connect_health as CH  # noqa: E402
import incident_desk as ID  # noqa: E402
import javis_core  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

if os.environ["JAVIS_STATE_DIR"] not in str(cfgmod.STATE_DIR):
    print(f"FAIL state dir is not the temp dir: {cfgmod.STATE_DIR}. STOP.")
    sys.exit(1)

# ---- 1. Model của Javis Core ----
cfgmod.update_settings({"model": {"main": {"provider": "anthropic-cli", "model": "opus"}, "groq_api_key": "gsk_test",
                                  "core_provider": "", "core_model": ""}})
store = main.get_store()
core = store.create_session(brain="brain", channel=javis_core.CHANNEL)
web = store.create_session(brain="brain")
store.set_pinned_model(core, "groq", "old-stamp")     # an old first-turn stamp of this one Core chat


def mcfg():
    return cfgmod.read_settings().get("model", {})


prov, _, _, model = main._chat_provider_for_session(mcfg(), store.get_session(core))
check("a Core chat with no Core pin follows the main model, its own old stamp is ignored",
      (prov, model) == ("anthropic-cli", "opus"), (prov, model))

client = TestClient(main.app, base_url="http://127.0.0.1:8080")
r = client.post(f"/sessions/{core}/model", data={"provider": "groq", "model": "qwen3-32b"})
check("picking a model in a Core chat pins Javis Core as a whole", r.status_code == 200 and r.json().get("scope") == "core" and
      mcfg().get("core_provider") == "groq" and mcfg().get("core_model") == "qwen3-32b", r.text)
check("...and clears the chat's own old stamp", not (store.get_session(core) or {}).get("pinned_provider"))
core2 = store.create_session(brain="brain", channel=javis_core.CHANNEL)
prov, kind, key, model = main._chat_provider_for_session(mcfg(), store.get_session(core2))
check("a new Core chat runs on the Core pin", (prov, kind, key, model) == ("groq", "api", "gsk_test", "qwen3-32b"),
      (prov, model))
prov, _, _, model = main._chat_provider_for_session(mcfg(), store.get_session(web))
check("an ordinary chat is not touched by the Core pin", (prov, model) == ("anthropic-cli", "opus"), (prov, model))
meta = client.get(f"/sessions/{core2}/meta").json()
check("meta of a Core chat shows the Core pin", meta.get("pinned_provider") == "groq" and meta.get("pinned_model") == "qwen3-32b" and
      meta.get("pin_ok") is True and meta.get("agent_slug") == javis_core.SLUG, meta)
cfgmod.update_settings({"model": {"main": {"provider": "anthropic-cli", "model": "sonnet"}}})
prov, _, _, model = main._chat_provider_for_session(mcfg(), store.get_session(core2))
check("changing the main model does not move a pinned Core", (prov, model) == ("groq", "qwen3-32b"), (prov, model))
r = client.post(f"/sessions/{core2}/model", data={"provider": "", "model": ""})
check("'Follow the main model' clears the Core pin", r.status_code == 200 and not mcfg().get("core_provider") and
      not mcfg().get("core_model"), mcfg())
prov, _, _, model = main._chat_provider_for_session(mcfg(), store.get_session(core))
check("then every Core chat follows the main model again, live", (prov, model) == ("anthropic-cli", "sonnet"), (prov, model))
meta = client.get(f"/sessions/{core}/meta").json()
check("meta of a Core chat following the main model shows no pin", not meta.get("pinned_provider"), meta)
cfgmod.update_settings({"model": {"core_provider": "openrouter", "core_model": "x/y"}})
prov, _, _, _ = main._chat_provider_for_session(mcfg(), store.get_session(core))
check("a broken Core pin (no key) falls back to the main model", prov == "anthropic-cli", prov)
cfgmod.update_settings({"model": {"core_provider": "", "core_model": ""}})
r = client.post(f"/sessions/{web}/model", data={"provider": "groq", "model": "m1"})
check("an ordinary chat still pins only itself", r.json().get("scope") is None and
      (store.get_session(web) or {}).get("pinned_provider") == "groq" and not mcfg().get("core_provider"), r.text)

src = (SERVER / "main.py").read_text(encoding="utf-8")
store.set_pinned_model(core2, "groq", "qwen3-32b")   # the first-turn stamp of a Core chat is harmless: ignored
prov, _, _, model = main._chat_provider_for_session(mcfg(), store.get_session(core2))
check("a first-turn stamp left on a Core chat does not pin it", (prov, model) == ("anthropic-cli", "sonnet"), (prov, model))
mp = (ROOT / "dashboard" / "model-picker.js").read_text(encoding="utf-8")
check("model bar: a Core chat's pin says it is for every Core chat", '"mpick.core_pin_title"' in mp)

# ---- 2. Đèn não: không dò chữ trong câu trả lời thường ----
check("a long answer is not an error line", not CH.looks_like_error_line("Đây là câu trả lời dài. " * 20 + "not logged in"))
check("a short sign-in error is an error line", CH.looks_like_error_line("Invalid API key · Please run /login"))
check("an empty result is not an error line", not CH.looks_like_error_line(""))
check("a long answer quoting a sign-in phrase does not light the engine light",
      not CH.flag_engine_auth_error("claude", "Câu trả lời bình thường. " * 20 + "Please run /login") and
      CH._engines.get("claude") is None)

sent = []


async def _down(text):
    sent.append(text)

CH.on_engine_down = _down
CH.engines_in_use = lambda: {"claude"}


async def _flag():
    CH.flag_engine_auth_error("claude", "Failed to authenticate: OAuth session expired")
    await asyncio.sleep(0)

asyncio.run(_flag())
check("a real sign-in failure is told once", len(sent) == 1, sent)
CH._engines.clear()                       # a restart forgets what is in memory
asyncio.run(_flag())
check("after a restart the same failure is not told again (saved on disk)", len(sent) == 1, sent)
CH.engine_run_ok("claude")
check("a recovery clears the saved notice", not CH._engine_notified_saved().get("claude"))
CH._engines.clear()
asyncio.run(_flag())
check("the next failure after a recovery is told again", len(sent) == 2, sent)

# ---- 3. Kiểm tra sau khởi động: "đang khởi động" không phải hỏng ----


class _Pool:
    def is_starting(self, spec):
        return False

    def init_error(self, spec):
        return ""


async def _check_one(conn, pool=None):
    return {"ok": False, "kind": "starting" if conn["id"] == "dang-tai" else "auth", "message": "x"}

CH.check_one = _check_one
CH.mcp_store.resolved = lambda *_a, **_k: [{"id": "dang-tai", "label": "A"}, {"id": "hong", "label": "B"}]
CH.mcp_client.co_server_de_dial = lambda c: True
CH.mcp_client._conn_spec = lambda c: {"key": c["id"]}
smoke = []


async def _conns(text):
    smoke.append(text)

CH.on_connections_down = _conns
res = asyncio.run(CH.startup_smoke("0.402.0", pool=_Pool(), retry_after=0))
check("a source still in its first download is not reported as broken",
      [f["id"] for f in res.get("failed") or []] == ["hong"] and len(smoke) == 1 and "B:" in smoke[0] and "A:" not in smoke[0],
      (res, smoke))

# ---- 4. Bàn sự cố: một sự cố "cần bạn" không bị báo lại mỗi lần hỏng ----
posts = []


async def _post(brain, text):
    posts.append(text)


async def _ask(prompt):
    return '{"action": "person", "message": "Cần đăng nhập lại."}'

desk = ID.IncidentDesk(ID.IncidentDeps(state_dir=lambda: Path(os.environ["JAVIS_STATE_DIR"]), ask=_ask, post=_post, retry={}))


async def _three():
    for _ in range(3):
        desk.report("loop", "kiem-tra-don", brain="brain", title="Kiểm tra đơn", error="not logged in")
        await desk.wait_idle()

asyncio.run(_three())
items = desk.list() if hasattr(desk, "list") else desk._load()
check("three failures of the same job: one incident, one notice, counted 3 times",
      len(posts) == 1 and len(items) == 1 and int(items[0].get("count") or 0) == 3 and items[0].get("status") == "needs_you",
      (posts, items))

# ---- 5. Zalo bị giành phiên: mốc báo nằm trong kho ----
zsrc = (SERVER / "zalo_personal_channel.py").read_text(encoding="utf-8")
check("the eviction notice time is kept in the inbox store, read back after a restart",
      'conversations.ghi_trang_thai(f"zalo_thrash_bell:{cid}"' in zsrc and 'conversations.doc_trang_thai(f"zalo_thrash_bell:{cid}"' in zsrc)

dashes = [chr(0x2014), chr(0x2013)]
check("no em or en dash in this test", not any(d in Path(__file__).read_text(encoding="utf-8") for d in dashes))

print()
if fails:
    raise SystemExit(f"FAIL {len(fails)}: " + "; ".join(fails[:6]))
print("TẤT CẢ PASS")
