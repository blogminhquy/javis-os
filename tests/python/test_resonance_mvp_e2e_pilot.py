"""Resonance MVP: pilot đầu-cuối qua ĐƯỜNG CHAT THẬT (nghiệm thu điều kiện "đi hết vòng trên host thật").

    JAVIS_RESONANCE_E2E=dry  python tests/python/test_resonance_mvp_e2e_pilot.py      # KHÔNG gọi model
    JAVIS_RESONANCE_E2E=real JAVIS_RESONANCE_PILOT_SETTINGS=<settings.json thật> \\
        python tests/python/test_resonance_mvp_e2e_pilot.py                            # gọi model, cần người dùng duyệt

Không đặt JAVIS_RESONANCE_E2E thì bỏ qua (CI và tests/run.py không gọi gì). Kịch bản và hạn mức đề xuất ở
docs/dev/resonance-mvp-e2e-pilot-plan.md.

Bộ chạy dựng server Javis THẬT từ checkout này (tiến trình riêng, cổng 7791), JAVIS_STATE_DIR và BRAINS_DIR tạm,
brain mặc định ("Brain Default", dashboard gọi tắt là "brain") bật Resonance, dữ liệu mô phỏng. Chỉ chép các ô CHỌN engine từ settings.json thật, không chép khoá
hay kênh nào (không Telegram, không Zalo: không gửi gì ra ngoài). Gián đoạn là GIẾT CẢ CÂY tiến trình server
(python.exe của .venv trên Windows là launcher có tiến trình con), không phải tắt êm.

- real: gửi MỘT tin chat qua /ws như dashboard -> bộ não chính tự quyết có gọi javis_goal -> giết server ngay sau
  lượt -> khởi động lại -> nhịp lập lịch làm việc bằng engine việc nền -> báo về đúng phiên -> giết và khởi động lại
  lần nữa (không báo lặp) -> bấm "Đạt yêu cầu" qua API như nút trên thẻ -> thành công, báo về đúng phiên.
  Trần lượt gọi model: JAVIS_RESONANCE_E2E_MAX_CALLS (mặc định 3: 1 lượt bộ não + tối đa 2 lượt việc nền). Vượt
  trần thì giết server ngay và ghi FAIL.
- dry: không gửi tin chat, không gọi model. Engine việc nền đặt là một provider bộ chọn chỉ chữ chặn sẵn. Mục tiêu
  được lập bằng đúng hàm tool javis_goal dùng (form_goal) vào kho của server. Kiểm hạ tầng của pilot: dựng/giết/khởi
  động lại server, WebSocket, nhịp lập lịch nhận lịch sau khởi động lại, báo về đúng phiên có biên nhận, không báo
  lặp sau khởi động lại, API thẻ (GET /goals, POST feedback) qua kiểm Origin.
JAVIS_RESONANCE_E2E_OUT: nơi ghi báo cáo JSON (không có đường dẫn cá nhân).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MODE = os.environ.get("JAVIS_RESONANCE_E2E", "").strip().lower()
if MODE not in ("dry", "real"):
    print("pilot đầu-cuối: bỏ qua (đặt JAVIS_RESONANCE_E2E=dry hoặc real để chạy)")
    print("\nOK")
    sys.exit(0)

PORT = int(os.environ.get("JAVIS_RESONANCE_E2E_PORT", "7791"))
MAX_CALLS = int(os.environ.get("JAVIS_RESONANCE_E2E_MAX_CALLS", "3"))
# Lượt bộ não: bộ chạy gửi ĐÚNG một tin chat ở chế độ real (một lượt bộ não, kể cả các vòng công cụ trong lượt đó).
BRAIN_TURNS_PLANNED = 1 if MODE == "real" else 0
# Phần còn lại của trần dành cho việc nền, server chặn TRƯỚC lượt gọi vượt trần (resonance_store.call_ceiling), số
# đã dùng nằm trong SQLite nên trần giữ qua mọi lần khởi động lại; bộ chạy truyền biến này cho MỖI tiến trình server.
CEILING = MAX_CALLS - BRAIN_TURNS_PLANNED
if CEILING < 0:
    print("FAIL pilot: trần nhỏ hơn số lượt bộ não đã định")
    sys.exit(1)


def _clean_env() -> dict:
    """Môi trường cho server sandbox: như một Javis bình thường của người dùng. Bỏ mọi biến của phiên Claude Code
    đang chạy bộ chạy này (CLAUDE*, ANTHROPIC*) và mọi khoá nhà cung cấp, để tiến trình `claude` của Javis tự dùng
    đăng nhập gói thuê bao của người dùng và không có đường nào sang API trả phí."""
    drop = ("CLAUDE", "ANTHROPIC", "OPENAI", "OPENROUTER", "GEMINI", "GOOGLE_API", "GROQ", "XAI", "OLLAMA", "CODEX",
            "AWS_BEARER")
    return {k: v for k, v in os.environ.items()
            if not k.upper().startswith(drop) and not k.upper().endswith(("_API_KEY", "_AUTH_TOKEN"))}
# Đường dẫn NGẮN: đường dẫn sâu làm ghi đầu ra lỗi write_failed trên Windows (MAX_PATH, ghi nhận ở M4).
BASE = Path(tempfile.mkdtemp(prefix="rse2e-", dir=os.environ.get("TEMP") or None)).resolve()
STATE, BRAINS = BASE / "state", BASE / "brains"
# Brain MẶC ĐỊNH của BRAINS_DIR: dashboard gửi tên tắt "brain" cho nó, pilot gửi đúng như vậy.
BRAIN = BRAINS / "Brain Default"
for d in (STATE, BRAIN / "Javis", BRAIN / "Notes"):
    d.mkdir(parents=True, exist_ok=True)
(BRAIN / "Javis" / "resonance.json").write_text('{"enabled": true}', encoding="utf-8")
KEEP = BRAIN / "Notes" / "ghi-chu-cu.md"
KEEP.write_text("Ghi chú cũ, không được xoá.\n", encoding="utf-8")
_keep_sha = hashlib.sha256(KEEP.read_bytes()).hexdigest()

if MODE == "real":
    src = os.environ.get("JAVIS_RESONANCE_PILOT_SETTINGS", "")
    if not src or not Path(src).is_file():
        print("FAIL pilot: thiếu JAVIS_RESONANCE_PILOT_SETTINGS trỏ tới settings.json thật")
        sys.exit(1)
    _m = (json.loads(Path(src).read_text(encoding="utf-8")).get("model") or {})
    MODEL = {k: _m[k] for k in ("auxiliary", "main", "engine", "claude_model") if k in _m}
else:
    # Bộ chọn chỉ chữ của Resonance chặn provider này (không có mắt chỉ chữ): việc nền không gọi model nào.
    MODEL = {"auxiliary": {"provider": "grok-cli", "model": "grok-dry"}}
(STATE / "settings.json").write_text(json.dumps({"model": MODEL}, ensure_ascii=False), encoding="utf-8", newline="\n")

os.environ["JAVIS_STATE_DIR"] = str(STATE)
import resonance as R  # noqa: E402  - sau khi đặt JAVIS_STATE_DIR
import resonance_store as RS  # noqa: E402
import sessions as SS  # noqa: E402

KEY = str(BRAIN.resolve())
P = RS.Principal("agent", "javis", KEY)
ORIGIN = f"http://127.0.0.1:{PORT}"
USER_MSG = ("(Dữ liệu mô phỏng để thử nghiệm.) Từ biên bản họp dưới đây, lo giúp mình một ghi chú "
            "Inbox/viec-tu-bien-ban.md liệt kê từng việc kèm người phụ trách và hạn chót. Không cần làm ngay trong "
            "lượt này, cứ làm ở nền, xong thì báo để mình xem lại rồi xác nhận. Đừng đụng tới Notes/ghi-chu-cu.md.\n"
            "Biên bản họp nhóm nội dung ngày 03/10: Lan soạn kế hoạch bài viết tháng 11, hạn thứ Sáu. Minh kiểm lại "
            "lịch đăng, hạn 10/10. Hà gửi bảng số liệu cho cả nhóm trước thứ Hai.")

_fails, _log = [], []


def check(name, cond, hard=True):
    print(("ok   " if cond else ("FAIL " if hard else "NOTE ")) + name)
    _log.append({"check": name, "ok": bool(cond), "hard": hard})
    if not cond and hard:
        _fails.append(name)


class Server:
    """Server Javis thật của checkout này. kill() giết CẢ CÂY tiến trình (mô phỏng sập máy, không tắt êm)."""

    def __init__(self):
        self.n, self.proc = 0, None

    def start(self, wait_s=120):
        self.n += 1
        env = {**_clean_env(), "JAVIS_PORT": str(PORT), "JAVIS_STATE_DIR": str(STATE), "BRAINS_DIR": str(BRAINS),
               "JAVIS_REQUIRE_LOGIN": "0", "PYTHONUTF8": "1", "JAVIS_RESONANCE_CALL_CEILING": str(CEILING)}
        log = open(BASE / f"server-{self.n}.log", "w", encoding="utf-8")
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self.proc = subprocess.Popen([sys.executable, "server/main.py"], cwd=str(ROOT), env=env, stdout=log,
                                     stderr=subprocess.STDOUT, creationflags=flags)
        import httpx
        t0 = time.time()
        while time.time() - t0 < wait_s:
            if self.proc.poll() is not None:
                raise RuntimeError(f"server thoát sớm, xem {BASE.name}/server-{self.n}.log")
            try:
                if httpx.get(f"{ORIGIN}/health", timeout=2).status_code == 200:
                    return time.time() - t0
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1)
        raise RuntimeError("server không lên kịp")

    def kill(self):
        if self.proc is None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)
        else:
            self.proc.kill()
        self.proc.wait(timeout=30)
        self.proc = None
        time.sleep(2)


SRV = Server()


def goal_store():
    return RS.GoalStore(STATE / "resonance.sqlite3")


def sess_store():
    return SS.SessionStore(STATE / "conversations.db")


def _all_goals():
    import sqlite3
    db = STATE / "resonance.sqlite3"
    if not db.exists():
        return []
    c = sqlite3.connect(str(db))
    ids = [r[0] for r in c.execute("SELECT id FROM goals WHERE brain_id=?", (KEY,)).fetchall()]
    c.close()
    st = goal_store()
    return [st.get(P, i) for i in ids]


def model_calls(brain_turns):
    return brain_turns + sum(g.calls_used for g in _all_goals())


def reports(sid):
    """Tin trợ lý trong phiên mang khối thẻ, kèm khoá báo cáo và biên nhận của host."""
    ss = sess_store()
    out = []
    for m in ss.get_messages(sid):
        if m["role"] != "assistant":
            continue
        for b in R.parse_goal_blocks(m.get("content") or ""):
            rk = b.get("report") or ""
            rc = ss.report_receipt(sid, rk, b["goal_id"]) if rk else None
            out.append({"message_id": m["id"], "goal_id": b["goal_id"], "report": rk, "receipt": bool(rc)})
    return out


def wait_until(pred, timeout, step=3):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return pred()


async def ws_hello():
    import websockets
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws", origin=ORIGIN, max_size=None) as ws:
        return json.loads(await asyncio.wait_for(ws.recv(), 20)).get("type")


async def ws_chat(message, timeout=900):
    """Gửi MỘT tin như dashboard, đọc khung tới turn_done. Trả (session_id, danh sách loại khung, tên tool đã gọi)."""
    import websockets
    frames, tools, sid = [], [], None
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws", origin=ORIGIN, max_size=None) as ws:
        await asyncio.wait_for(ws.recv(), 20)
        await ws.send(json.dumps({"message": message, "brain": "brain"}))
        t0 = time.time()
        while time.time() - t0 < timeout:
            o = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            frames.append(o.get("type"))
            sid = sid or o.get("session_id")
            if o.get("type") in ("tool_call", "tool"):
                tools.append(str(o.get("name") or o.get("tool") or "")[:80])
            if o.get("type") == "turn_done":
                break
    return sid, frames, tools


def http(method, path, **kw):
    import httpx
    r = httpx.request(method, f"{ORIGIN}{path}", params={"brain": "brain"}, headers={"Origin": ORIGIN}, timeout=30,
                      **kw)
    try:
        return r.status_code, r.json()
    except Exception:  # noqa: BLE001
        return r.status_code, {}


rep = {"mode": MODE, "max_calls": MAX_CALLS, "brain_turns_planned": BRAIN_TURNS_PLANNED,
       "background_ceiling": CEILING, "env_dropped": sorted({k.split("_")[0] for k in os.environ} - {
           k.split("_")[0] for k in _clean_env()}), "steps": {}}
brain_turns = 0
t_start = time.time()
try:
    rep["steps"]["start_1_s"] = round(SRV.start(), 1)
    check("server thật lên được, WebSocket /ws nhận kết nối qua kiểm Origin", asyncio.run(ws_hello()) == "hello")

    # ───────────── Bước 1: tin chat (real) hoặc lập mục tiêu bằng đúng hàm của tool (dry) ─────────────
    if MODE == "real":
        t0 = time.time()
        if BRAIN_TURNS_PLANNED + CEILING > MAX_CALLS:
            raise SystemExit("dừng: lượt bộ não cộng trần việc nền vượt trần đã duyệt")
        brain_turns = 1          # tính TRƯỚC khi gửi: lượt bộ não được giữ chỗ trong trần
        sid, frames, tools = asyncio.run(ws_chat(USER_MSG))
        rep["steps"]["chat_turn_s"] = round(time.time() - t0, 1)
        rep["frames"] = {k: frames.count(k) for k in sorted(set(f for f in frames if f))}
        rep["tools_called"] = tools
        check("lượt chat kết thúc (turn_done) và có session_id", bool(sid) and frames and frames[-1] == "turn_done")
    else:
        ss = sess_store()
        sid = ss.get_or_create(None, brain=KEY, engine="dry", model="dry")
        mid = ss.append_message(sid, "user", USER_MSG)
        prop = {"understanding": "Ghi chú việc từ biên bản họp, mỗi việc có người phụ trách và hạn",
                "relevant_quote": "lo giúp mình một ghi chú", "stage": "delivery",
                "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"},
                "criteria": [{"description": "Ghi chú có đủ ba người", "evaluator": "artifact_contract",
                              "params": {"path": "Inbox/viec-tu-bien-ban.md", "must_contain": ["Lan", "Minh", "Hà"]}},
                             {"description": "Mình xác nhận ghi chú dùng được", "evaluator": "human_confirmation"}]}
        asyncio.run(R.form_goal(R.message_ref(sid, mid), {
            "principal": P, "brain_root": KEY, "session_id": sid, "message_id": mid, "user_text": USER_MSG,
            "constraints": [], "budget_calls": 3, "proposal": prop},
            R.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=R.CallBudget(0), store=goal_store())))
    rep["session_id_hash"] = hashlib.sha256(str(sid).encode()).hexdigest()[:12]
    gs = [g for g in _all_goals() if g.session_id == sid]
    rep["goal_created"] = bool(gs)
    check("bộ não tự lập ĐÚNG MỘT mục tiêu qua javis_goal, gắn đúng phiên chat" if MODE == "real"
          else "mục tiêu lập bằng form_goal, gắn đúng phiên", len(gs) == 1)
    if not gs:
        raise SystemExit("dừng: không có mục tiêu để theo dõi (ghi nhận như kết quả pilot, không thử lại)")
    g = gs[0]
    rep["goal"] = {"understanding": g.understanding, "stage": g.stage, "mode": g.mode, "horizon": g.horizon,
                   "criteria": [{k: c.get(k) for k in ("id", "evaluator", "description", "params")} for c in g.criteria],
                   "guards": [x.get("description") for x in g.guards], "budget_calls": g.budget_calls}
    it = goal_store().get_intent(P, g.intent_id) or {}
    check("ý định gốc là NGUYÊN lời người dùng của tin vừa gửi", "Biên bản họp nhóm nội dung" in str(it.get("text")))
    if MODE == "real":
        check("thẻ mục tiêu được đặt vào đúng phiên sau lượt, có biên nhận của host",
              bool(wait_until(lambda: [r for r in reports(sid) if r["goal_id"] == g.id and r["receipt"]], 20)))
    check("chưa có lượt việc nền nào trước khi server bị giết", not [a for a in goal_store().actions(P, g.id)
                                                                   if a["kind"] == "work"], hard=False)

    # ───────────── Bước 2: GIẾT server (gián đoạn), khởi động lại; nhịp lập lịch phải tự làm tiếp ─────────────
    SRV.kill()
    rep["steps"]["start_2_s"] = round(SRV.start(), 1)

    def _settled():
        if model_calls(brain_turns) > MAX_CALLS:
            return "over"
        acts = [a for a in goal_store().actions(P, g.id) if a["kind"] == "work" and a["status"] != "running"]
        if not acts:
            return None
        pend = [r for r in goal_store().outbox_pending(500) if r["goal_id"] == g.id]
        return "done" if not pend else None

    t0 = time.time()
    st = wait_until(_settled, 300)
    rep["steps"]["work_after_restart_s"] = round(time.time() - t0, 1)
    if st == "over":
        SRV.kill()
        check(f"trần lượt gọi model ({MAX_CALLS}) không bị vượt", False)
        raise SystemExit("dừng: vượt trần lượt gọi")
    acts = [a for a in goal_store().actions(P, g.id) if a["kind"] == "work"]
    check("sau khởi động lại, nhịp lập lịch tự làm lượt việc nền (không cần ai gọi lại)", bool(acts))
    rs = goal_store().run_state(P, g.id) or {}
    rep["after_work"] = {"run_state": rs.get("run_state"), "block_reason": rs.get("block_reason"),
                         "status": goal_store().get(P, g.id).status,
                         "receipts": [{k: (a["receipt"] or {}).get(k) for k in
                                       ("status", "error_code", "engine", "tool_calls_observed", "output_sha256",
                                        "usage")} for a in acts]}
    if MODE == "real":
        w = acts[-1]["receipt"]
        check("lượt việc nền: receipt succeeded, đúng provider đã chọn, không gọi công cụ",
              w.get("status") == "succeeded" and w.get("engine", {}).get("provider") ==
              w.get("engine", {}).get("requested_provider") and w.get("tool_calls_observed") == 0)
        deliv = R._deliverable_rel(goal_store().get(P, g.id))
        check("sản phẩm được đăng vào brain đúng chỗ tiêu chí khai", bool(deliv) and (BRAIN / deliv).is_file(),
              hard=False)
    else:
        check("dry: engine việc nền bị chặn trước khi gọi model, mục tiêu blocked có lý do",
              rs.get("run_state") == "blocked" and goal_store().get(P, g.id).calls_used == 0)
    rpt1 = reports(sid)
    check("tin báo của lượt nền về ĐÚNG phiên chat, mỗi tin có biên nhận của host",
          any(r["report"].startswith("outbox:") for r in rpt1) and all(r["receipt"] for r in rpt1 if r["report"]))

    # ───────────── Bước 3: giết và khởi động lại lần nữa: không báo lặp, không gọi thêm ─────────────
    calls_before = model_calls(brain_turns)
    SRV.kill()
    rep["steps"]["start_3_s"] = round(SRV.start(), 1)
    time.sleep(75)   # hơn hai nhịp lập lịch (30 giây)
    rpt2 = reports(sid)
    keys = [r["report"] for r in rpt2 if r["report"]]
    check("sau khởi động lại: không có tin báo lặp (khoá báo cáo duy nhất)", len(keys) == len(set(keys)))
    check("sau khởi động lại: không gọi thêm model khi không có gì tới hạn", model_calls(brain_turns) == calls_before)

    # ───────────── Bước 4: người dùng bấm trên thẻ (qua API như dashboard) ─────────────
    code, body = http("GET", f"/goals/{g.id}")
    v = body.get("goal") or {}
    check("API thẻ GET /goals/{id} trả trạng thái sống của mục tiêu", code == 200 and v.get("goal_id") == g.id)
    human = [c for c in v.get("criteria", []) if c.get("evaluator") == "human_confirmation"]
    if MODE == "real" and human and v.get("artifact_ref"):
        code, body = http("POST", f"/goals/{g.id}/feedback",
                          json={"kind": "outcome_accepted", "expected_revision": v["revision"],
                                "criterion_id": human[0]["id"], "artifact_ref": v["artifact_ref"],
                                "idempotency_key": f"pilot-accept-{g.id}"})
        check("bấm Đạt yêu cầu qua API (kiểm Origin, đúng revision, đúng bản sản phẩm): 200", code == 200)
        done = wait_until(lambda: goal_store().get(P, g.id).status == "succeeded"
                          and not [r for r in goal_store().outbox_pending(500) if r["goal_id"] == g.id], 120)
        check("sau xác nhận: host đánh giá lại và kết luận thành công, không gọi model thêm",
              bool(done) and model_calls(brain_turns) == calls_before)
        check("tin báo thành công về đúng phiên, có biên nhận",
              len([r for r in reports(sid) if r["report"].startswith("outbox:")]) > len(
                  [r for r in rpt2 if r["report"].startswith("outbox:")]))
    elif MODE == "real":
        check("mục tiêu có tiêu chí người dùng duyệt và có sản phẩm để duyệt", False, hard=False)
    else:
        code, body = http("POST", f"/goals/{g.id}/feedback",
                          json={"kind": "goal_fit_confirmed", "expected_revision": v.get("revision", 1)})
        check("dry: POST feedback qua kiểm Origin của server thật: 200", code == 200)
    check("ghi chú cũ (Notes/ghi-chu-cu.md) còn nguyên",
          KEEP.is_file() and hashlib.sha256(KEEP.read_bytes()).hexdigest() == _keep_sha)
    check(f"tổng lượt gọi model trong trần {MAX_CALLS}", model_calls(brain_turns) <= MAX_CALLS)
    check(f"lượt việc nền trong trần server {CEILING} (chặn trước lượt gọi)",
          model_calls(brain_turns) - brain_turns <= CEILING)
except SystemExit as e:
    print(f"DỪNG: {e}")
except Exception as e:  # noqa: BLE001
    check(f"bộ chạy không lỗi ({type(e).__name__}: {e})", False)
finally:
    SRV.kill()
    rep["model_calls"] = model_calls(brain_turns)
    rep["seconds_total"] = round(time.time() - t_start, 1)
    rep["checks"] = _log
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True,
                              timeout=10).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "server", "system"], cwd=str(ROOT),
                                    capture_output=True, text=True, timeout=10).stdout.strip())
    except Exception:  # noqa: BLE001
        head, dirty = "", None
    rep["commit"], rep["server_dirty"] = head, dirty
    print("E2E_REPORT " + json.dumps({k: rep[k] for k in ("mode", "model_calls", "seconds_total") if k in rep},
                                     ensure_ascii=False))
    outp = os.environ.get("JAVIS_RESONANCE_E2E_OUT")
    if outp:
        Path(outp).write_text(json.dumps(rep, ensure_ascii=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    if not os.environ.get("JAVIS_RESONANCE_E2E_KEEP"):
        shutil.rmtree(BASE, ignore_errors=True)

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
