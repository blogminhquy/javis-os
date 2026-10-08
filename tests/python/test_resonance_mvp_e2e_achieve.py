"""Resonance MVP: pilot đầu-cuối lần 3, mục tiêu ACHIEVE sửa qua phản hồi, qua ĐƯỜNG CHAT THẬT.

    JAVIS_RESONANCE_E2E_ACHIEVE=dry  python tests/python/test_resonance_mvp_e2e_achieve.py   # KHÔNG gọi model
    JAVIS_RESONANCE_E2E_ACHIEVE=real JAVIS_RESONANCE_PILOT_SETTINGS=<settings.json thật> \\
        JAVIS_RESONANCE_E2E_OUT=<báo cáo.json> python tests/python/test_resonance_mvp_e2e_achieve.py  # cần người dùng duyệt

Không đặt biến thì bỏ qua (CI và tests/run.py không gọi gì). Kịch bản, hạn mức, hợp đồng: docs/dev/resonance-mvp-e2e-
pilot-plan.md, mục "Đề xuất lần chạy 3". Bộ chạy maintain cũ (test_resonance_mvp_e2e_pilot.py) giữ nguyên làm hồ sơ hai
lần chạy trước; phần hạ tầng (server thật, cổng xác thực) chép từ đó, không đổi luật.

Hạn mức chia theo GIAI ĐOẠN (review đường công cụ, điểm 1), tối đa 4 lượt engine cấp host:
- lượt chat: sổ TurnLedger, tối đa 2, giữ chỗ TRƯỚC mỗi lần gửi, hết giờ hay lỗi vẫn tính, không thử lại;
- việc nền: trần TÍCH LUỸ JAVIS_RESONANCE_CALL_CEILING=1 cho mọi server tới hết lượt chat góp ý (S0 tới S4), =2 cho
  server sau đó (S5, S6). Sổ không bao giờ đặt lại. Lượt chat góp ý chạy trên server có nhịp TẠM DỪNG, nên lịch làm lại
  chỉ được nhận sau khi server giai đoạn 2 lên.

Các bước (real):
S0 server A (nhịp dừng, trần 1): cổng xác thực, không gọi model.
S1 lượt chat 1. Bộ não tự quyết. Không lập mục tiêu, lập hai mục tiêu, hay giao Kanban: ghi nhận, lưu file đã ghi, DỪNG.
S2 giết A, dựng B (nhịp chạy, trần 1): bản đầu, đăng, báo về phiên, rồi chờ người dùng mà không gọi thêm.
S3 giết B, dựng C (nhịp chạy, trần 1): trạng thái còn nguyên, không báo lặp, không gọi thêm. Giết C, dựng D (nhịp dừng).
S4 lượt chat 2 (góp ý) trên D: phải nối vào CÙNG mục tiêu (revision +1, ý định mới là lời góp ý). Không thì DỪNG.
S5 giết D, dựng E (nhịp chạy, trần 2): đúng một lượt bản sửa, đăng, báo về phiên, chờ người dùng.
S6 bấm "Đạt yêu cầu" qua API cho TỪNG tiêu chí người dùng xác nhận của revision hiện hành (thao tác MÔ PHỎNG, chỉ kiểm
   đường API; không phải con người đã nghiệm thu nội dung).
Kết luận: kỹ thuật đạt thì `pending_content_review`: người review đọc hai bản đã lưu nguyên vẹn (hash) và tự chốt.

A1 (Cộng hưởng theo từng trợ lý, review tích hợp PR #590): pilot chạy trong PHIÊN TRỢ LÝ đã bật, không còn công tắc
brain. Brain tạm có một trợ lý tạm (AGENT_SLUG, không chọn model riêng nên chạy bằng bộ não chính đã duyệt). Chặng S0b
(không gọi model) kiểm ba cửa: chat thường bị chặn, trợ lý tắt bị chặn, bật qua API của chủ dự án thì phiên trợ lý
dùng được. Prompt phiên trợ lý KHÁC prompt chat thường của pilot 5 (không có CLAUDE.md): kết quả pilot không suy ngược
cho chat thường.
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

MODE = os.environ.get("JAVIS_RESONANCE_E2E_ACHIEVE", "").strip().lower()
if MODE not in ("dry", "real"):
    print("pilot achieve: bỏ qua (đặt JAVIS_RESONANCE_E2E_ACHIEVE=dry hoặc real để chạy)")
    print("\nOK")
    sys.exit(0)

sys.path.insert(0, str(Path(__file__).parent))
import _e2e_pilot_guard as G  # noqa: E402
import _e2e_achieve_harness as H  # noqa: E402

PORT = int(os.environ.get("JAVIS_RESONANCE_E2E_PORT", "7792"))
CHAT_LIMIT = 2 if MODE == "real" else 0
PHASE_CEILING = {1: 1, 2: 2}            # trần TÍCH LUỸ việc nền theo giai đoạn
MAX_CALLS = CHAT_LIMIT + PHASE_CEILING[2]
BASE = Path(tempfile.mkdtemp(prefix="rsach-", dir=os.environ.get("TEMP") or None)).resolve()
STATE, BRAINS = BASE / "state", BASE / "brains"
BRAIN = BRAINS / "Brain Default"
for d in (STATE, BRAIN / "Javis", BRAIN / "agents"):
    d.mkdir(parents=True, exist_ok=True)
# A1: không bật công tắc brain cũ (nó không còn cấp quyền). Trợ lý tạm: vai trung lập, không chọn model riêng.
AGENT_SLUG = "tro-ly-tai-lieu"
AGENT_MD = ("---\nname: Trợ lý tài liệu\nrole: Soạn và sửa tài liệu hướng dẫn nội bộ\n---\n"
            "Bạn soạn và sửa tài liệu hướng dẫn nội bộ theo lời chủ dặn.\n")
(BRAIN / "agents" / f"{AGENT_SLUG}.md").write_text(AGENT_MD, encoding="utf-8", newline="\n")

OUT = os.environ.get("JAVIS_RESONANCE_E2E_OUT", "")
if MODE == "real" and not OUT:
    print("FAIL pilot: chế độ real cần JAVIS_RESONANCE_E2E_OUT (báo cáo và bản lưu sản phẩm cho người review)")
    sys.exit(1)

if MODE == "real":
    src = os.environ.get("JAVIS_RESONANCE_PILOT_SETTINGS", "")
    if not src or not Path(src).is_file():
        print("FAIL pilot: thiếu JAVIS_RESONANCE_PILOT_SETTINGS trỏ tới settings.json thật")
        sys.exit(1)
    _m = (json.loads(Path(src).read_text(encoding="utf-8")).get("model") or {})
    MODEL = {k: _m[k] for k in ("auxiliary", "main", "engine", "claude_model") if k in _m}
else:
    MODEL = {"auxiliary": {"provider": "grok-cli", "model": "grok-dry"}}   # việc nền bị chặn, không gọi model
assert not any(k in MODEL for k in ("claude_auth", "anthropic_api_key")), "settings sandbox không được có chế độ API key"
(STATE / "settings.json").write_text(json.dumps({"model": MODEL}, ensure_ascii=False), encoding="utf-8", newline="\n")

os.environ["JAVIS_STATE_DIR"] = str(STATE)
import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402
import sessions as SS  # noqa: E402

KEY = str(BRAIN.resolve())
P = RS.Principal("agent", "javis", KEY)
ORIGIN = f"http://127.0.0.1:{PORT}"

# ───────────── Đầu vào ĐÓNG BĂNG (review đường công cụ, điểm 2): không chọn dữ liệu lúc chạy ─────────────
DELIV = "Docs/huong-dan-nhan-hang.md"
USER_MSG = (
    "(Dữ liệu mô phỏng để thử nghiệm.) Anh cần một bản hướng dẫn nhận hàng ở kho cho nhân viên mới, viết từ mấy ghi "
    "chú dưới đây. Em lo việc này giúp anh tới khi anh thấy dùng được thì thôi: làm bản đầu, tự rà xem đủ những gì anh "
    "dặn chưa rồi báo anh; anh sẽ góp ý dần, em sửa tiếp theo góp ý. Lưu ở Docs/huong-dan-nhan-hang.md. Anh dặn: viết "
    "cho người chưa làm bao giờ, các bước đánh số, có mục \"Lỗi hay gặp\".\n"
    "Ghi chú:\n"
    "- Xe tới thì đếm số kiện trước khi cho tài xế đi.\n"
    "- Đối chiếu từng dòng hàng trên phiếu giao với hàng thực nhận: mã hàng, số lượng.\n"
    "- Thùng móp, ướt hoặc rách thì để riêng, ghi vào phiếu giao là hàng hỏng.\n"
    "- Chỉ ký nhận sau khi đã đếm và đối chiếu xong; thiếu hay hỏng thì ghi rõ cạnh chữ ký.\n"
    "- Nhập số thực nhận vào sổ kho trong ngày.\n"
    "- Gặp gì không chắc thì gọi anh Tùng, quản lý kho.")
FEEDBACK_MSG = ("Anh xem bản đầu rồi. Bước đối chiếu phiếu giao khó hiểu quá, em thêm một ví dụ cụ thể, và thêm bước "
                "chụp ảnh hàng hỏng trước khi ký.")
# Điều người review kiểm trên hai bản đã lưu (KHÔNG chấm tự động): bản đầu theo lời giao, bản sửa theo góp ý và vẫn giữ
# các yêu cầu cũ.
REVIEW_CHECKLIST = {
    "draft1": ["dành cho người chưa làm bao giờ", "các bước đánh số", "có mục \"Lỗi hay gặp\"",
               "đủ sáu ý của ghi chú (đếm kiện, đối chiếu phiếu, hàng hỏng để riêng, ký sau khi đếm, nhập sổ trong "
               "ngày, gọi anh Tùng)"],
    "draft2": ["bước đối chiếu phiếu giao có một ví dụ cụ thể", "có bước chụp ảnh hàng hỏng, đặt TRƯỚC bước ký",
               "vẫn giữ mọi yêu cầu của bản đầu"]}

APPROVED = (json.loads(os.environ["JAVIS_RESONANCE_E2E_APPROVED"]) if os.environ.get("JAVIS_RESONANCE_E2E_APPROVED")
            else {"main": {"provider": "anthropic-cli", "model": "claude-opus-5-5"},
                  "aux": {"provider": "anthropic-cli", "model": "sonnet"}, "claude_model": "claude-opus-5-5"}
            if MODE == "real" else {"aux": {"provider": "grok-cli"}})
BG_CWD = STATE / "resonance_cwd"
BG_CWD.mkdir(parents=True, exist_ok=True)
PILOT_VARS = ("JAVIS_RESONANCE_TICK_PAUSED", "JAVIS_RESONANCE_CALL_CEILING", "JAVIS_CLAUDE_CLI", "JAVIS_CLAUDE_BIN",
              "JAVIS_STATE_DIR", "BRAINS_DIR", "JAVIS_PORT")
TURNS = G.TurnLedger(STATE / "pilot-chat-turns.json", CHAT_LIMIT)

# Kiểm và CỔNG CHI PHÍ (review bộ chạy achieve, P2-1): mọi kiểm hỏng, kỹ thuật hay hợp đồng, đóng cổng; dựng server,
# gửi tin chat và bấm xác nhận đều đi qua cổng nên không cấp thêm lượt sau khi tiền điều kiện đã hỏng.
CHECKS = H.Checks()
check = CHECKS.check
_fails, _contract, _log = CHECKS.fails, CHECKS.contract, CHECKS.log


class Stop(Exception):
    """Dừng theo hợp đồng (bộ não không đi đường mục tiêu): ghi nhận, không thử lại."""


ENV0 = {k: v for k, v in G.clean_env(dict(os.environ)).items() if k not in PILOT_VARS}


def resolve_engines() -> dict:
    code = ("import json, sys; sys.path.insert(0, 'server'); import aux_engine, config; "
            "m = (config.read_settings().get('model') or {}); "
            "print(json.dumps({'main': aux_engine.main_spec(), 'aux': aux_engine.read_spec(), "
            "'claude_model': m.get('claude_model')}))")
    cp = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env={**ENV0, "JAVIS_STATE_DIR": str(STATE)},
                        capture_output=True, text=True, timeout=120)
    try:
        return json.loads((cp.stdout or "").strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {}


def _resolve_cli() -> str:
    cp = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, 'server'); "
                         "from claude_cli import tim_binary; print(tim_binary('claude') or '')"],
                        cwd=str(ROOT), env=ENV0, capture_output=True, text=True, timeout=60)
    return (cp.stdout or "").strip().splitlines()[-1] if (cp.stdout or "").strip() else ""


def _auth_at(cli: str, cwd: Path) -> dict:
    st = subprocess.run([cli, "auth", "status", "--json"], cwd=str(cwd), env=ENV0, capture_output=True, text=True,
                        timeout=60)
    return json.loads(st.stdout or "{}")


def auth_gate(cli: str) -> dict:
    """Cùng cổng với bộ chạy maintain (review e2e P1-2 và vòng 2), không gọi model."""
    out = {"cli_found": bool(cli), "ok": False, "why": ""}
    eng = resolve_engines()
    out["engines"], out["approved"] = eng, APPROVED
    ok_e, why_e = G.check_engines(eng, APPROVED)
    if not ok_e:
        out["why"] = "engine sẽ chạy khác cấu hình đã duyệt: " + why_e
        return out
    if not cli:
        out["why"] = "không tìm thấy binary claude"
        return out
    try:
        ver = subprocess.run([cli, "--version"], cwd=str(BRAIN), env=ENV0, capture_output=True, text=True, timeout=60)
        out["cli_version"] = (ver.stdout or "").strip()[:60]
        st = {"chat": _auth_at(cli, BRAIN), "background": _auth_at(cli, BG_CWD)}
    except Exception as e:  # noqa: BLE001
        out["why"] = f"không chạy được auth status: {type(e).__name__}"
        return out
    out["auth"] = {k: G.auth_metadata(v) for k, v in st.items()}
    for k, v in st.items():
        ok, why = G.check_auth_status(v)
        if not ok:
            out["why"] = f"{k}: {why}"
            return out
    cfg_dir = Path(st["chat"].get("configDirectory") or (Path.home() / ".claude"))
    paths = G.settings_paths(cfg_dir, BRAIN) + G.settings_paths(cfg_dir, BG_CWD)[2:4]
    out["settings"] = G.scan_settings(paths)
    out["managed_sources"] = G.managed_sources(cfg_dir)
    out["not_assessed"] = G.ancillary_sources(paths)
    if out["settings"]["risky"]:
        out["why"] = "nguồn settings có apiKeyHelper hay env chọn nhà cung cấp/khoá"
        return out
    if out["managed_sources"]:
        out["why"] = "có nguồn settings do quản trị đặt; môi trường này pilot chưa hỗ trợ"
        return out
    out["ok"] = True
    return out


def start_server(phase: int, tick_paused: bool):
    return SRV.start(phase, tick_paused, {"JAVIS_STATE_DIR": str(STATE), "BRAINS_DIR": str(BRAINS)})


def goal_store():
    return RS.GoalStore(STATE / "resonance.sqlite3")


def sess_store():
    return SS.SessionStore(STATE / "conversations.db")


def _sql(q, args=()):
    import sqlite3
    db = STATE / "resonance.sqlite3"
    if not db.exists():
        return []
    c = sqlite3.connect(str(db))
    try:
        return c.execute(q, args).fetchall()
    except Exception:  # noqa: BLE001
        return []
    finally:
        c.close()


def all_goals():
    st = goal_store()
    return [st.get(P, r[0]) for r in _sql("SELECT id FROM goals WHERE brain_id=?", (KEY,))]


def background_calls():
    n = int((_sql("SELECT COALESCE(SUM(calls_used),0) FROM goals") or [(0,)])[0][0])
    n += int((_sql("SELECT COUNT(*) FROM call_ledger WHERE status='used'") or [(0,)])[0][0])
    return n


def work_actions(gid, revision=None):
    return [a for a in goal_store().actions(P, gid) if a["kind"] == "work"
            and (revision is None or a["revision"] == revision)]


def notices(gid):
    return H.outbox_rows(_sql("SELECT id, goal_id, kind, payload_json, delivered_at FROM outbox WHERE goal_id=? "
                              "ORDER BY id", (gid,)))


def notice_in_session(sid_, gid, kind, revision):
    """Tin MỚI của đúng giai đoạn (loại, revision) có trong đúng phiên, kèm biên nhận (review bộ chạy, P2-2)."""
    return H.stage_notice(notices(gid), reports(sid_), gid, kind, revision)


def reports(sid):
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


def kanban_tasks():
    import sqlite3
    try:
        kc = sqlite3.connect(str(STATE / "kanban.sqlite3"))
        rows = kc.execute("SELECT title, status FROM tasks").fetchall()
        kc.close()
        return [{"title": r[0], "status": r[1]} for r in rows]
    except Exception:  # noqa: BLE001
        return []


def wait_until(pred, timeout, step=3):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return pred()


def _cut(v, n=3000):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + f"...(+{len(s) - n})"


async def ws_hello():
    import websockets
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws", origin=ORIGIN, max_size=None) as ws:
        return json.loads(await asyncio.wait_for(ws.recv(), 20)).get("type")


async def _ws_chat(message, session_id=None, timeout=900):
    import websockets
    frames, tools, answer, sid, done = [], [], [], session_id, {}
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws", origin=ORIGIN, max_size=None) as ws:
        await asyncio.wait_for(ws.recv(), 20)
        payload = {"message": message, "brain": "brain"}
        if session_id:
            payload["session_id"] = session_id
        await ws.send(json.dumps(payload))
        t0 = time.time()
        while time.time() - t0 < timeout:
            o = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            t = o.get("type")
            frames.append(t)
            sid = sid or o.get("session_id")
            if t in ("tool_call", "tool", "tool_result"):
                tools.append({k: _cut(o.get(k)) for k in ("type", "tool", "name", "detail", "content", "input")
                              if o.get(k) not in (None, "")})
            if t in ("response", "stream", "text") and o.get("content"):
                answer.append(str(o.get("content")))
            if t == "turn_done":
                done = {"engine_status": o.get("engine_status"), "engine_error": o.get("engine_error"),
                        "turn_status": o.get("turn_status")}
                break
    return sid, frames, tools, "".join(answer)[-6000:], done


TOKEN_MIN_S = 600


def token_ready(label):
    """Kiểm NGAY TRƯỚC khi gửi (pilot lần 4): token đăng nhập Claude còn đủ hạn cho lượt này, để lượt không phải làm
    mới token giữa chừng (lúc đó dễ đụng một tiến trình Claude Code khác cũng đang làm mới). Chỉ đọc trường expiresAt qua
    claude_token_gate.han_token, không đọc hay ghi token. Còn dưới TOKEN_MIN_S hay không đọc được hạn: ghi lỗi kỹ thuật,
    cổng chi phí đóng, lượt KHÔNG được gửi và không giữ chỗ trong sổ. Đây là giảm rủi ro, không bảo đảm hết xung đột."""
    if MODE != "real":
        return True
    sys.path.insert(0, str(Path(ROOT) / "server"))
    import claude_token_gate
    exp = claude_token_gate.han_token()
    left = round(exp - time.time()) if exp else None
    rep["stages"].setdefault("token_check", {})[label] = left
    return check(f"{label} token đăng nhập còn ít nhất {TOKEN_MIN_S} giây trước khi gửi (còn {left})",
                 left is not None and left >= TOKEN_MIN_S)


def chat_turn(label, message, session_id=None):
    """MỘT lượt chat qua cổng chi phí và sổ lượt (H.chat_turn): giữ chỗ trước khi gửi, lỗi hay hết giờ vẫn tính."""
    token_ready(label)              # hỏng thì H.chat_turn dừng ở cổng, trước khi giữ chỗ hay gửi
    before = G.snapshot_files(BRAIN)
    t0 = time.time()
    try:
        (sid_, frames, tools, answer, done), status = H.chat_turn(CHECKS, TURNS, label,
                                                             lambda: asyncio.run(_ws_chat(message, session_id)))
    except H.GateClosed as e:
        # Lượt hỏng vẫn để lại trace trong báo cáo (khung, công cụ, câu trả lời, trạng thái engine) trước khi dừng.
        res = getattr(e, "result", None)
        if res is not None:
            rep["stages"][label] = {"seconds": round(time.time() - t0, 1), "turn_done": res[4],
                                    "frames": {k: res[1].count(k) for k in sorted(set(f for f in res[1] if f))},
                                    "tool_frames": res[2], "final_answer": res[3],
                                    "files_written": G.snapshot_diff(before, G.snapshot_files(BRAIN))}
        raise
    after = G.snapshot_files(BRAIN)
    return sid_, {"seconds": round(time.time() - t0, 1), "ledger_status": status, "turn_done": done,
                  "frames": {k: frames.count(k) for k in sorted(set(f for f in frames if f))},
                  "completed": status == "done",
                  "tool_frames": tools, "search_calls": G.search_calls(tools),
                  "goal_or_task_calls": G.goal_tool_calls(tools),
                  "files_written": G.snapshot_diff(before, after), "final_answer": answer,
                  # Danh sách tool trong tin `init` của Claude Code không đọc được từ ngoài mà không đổi mã sản phẩm.
                  "init_tool_list": "not_observable"}


def http(method, path, params_extra=None, **kw):
    import httpx
    r = httpx.request(method, f"{ORIGIN}{path}", params={"brain": "brain", **(params_extra or {})},
                      headers={"Origin": ORIGIN}, timeout=30, **kw)
    try:
        return r.status_code, r.json()
    except Exception:  # noqa: BLE001
        return r.status_code, {}


def _sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest() if p and Path(p).is_file() else ""


def _sha_text(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def preserve(tag):
    """Lưu NGUYÊN VẸN file sản phẩm (nếu có) ra cạnh báo cáo, kể cả khi dừng sớm (review pilot lần 2)."""
    f = BRAIN / DELIV
    if not OUT or not f.is_file():
        return {"saved": "", "sha256": _sha_file(f), "ok": False, "exists": f.is_file()}
    out = G.preserve_artifact(f, Path(OUT).with_name(Path(OUT).stem + f"-{tag}.md"))
    out["exists"] = True
    return out


def preserve_work_outputs(gid):
    """Xem H.preserve_work_outputs (review mã bàn giao, P2-1): lưu cả bản chưa có receipt, nhãn unverified."""
    return H.preserve_work_outputs(goal_store(), P, gid, DELIV, OUT, lambda src, label: G.preserve_artifact(
        src, Path(OUT).with_name(Path(OUT).stem + f"-{label}.md")))


def goal_view(g):
    it = goal_store().get_intent(P, g.intent_id) or {}
    return {"id": g.id, "revision": g.revision, "status": g.status, "mode": g.mode, "stage": g.stage,
            "understanding": g.understanding, "horizon": g.horizon, "deliverable": R._deliverable_rel(g),
            "criteria": [{k: c.get(k) for k in ("id", "evaluator", "description", "params")} for c in g.criteria],
            "constraints": list(g.constraints), "intent_sha": _sha_text(str(it.get("text") or "")),
            "prev_intent_id": it.get("prev_intent_id"), "intent_id": g.intent_id}


def _routing_versions():
    out = {}
    out["agent_file"] = _sha_file(BRAIN / "agents" / f"{AGENT_SLUG}.md")[:16]
    for name, p in (("repo_CLAUDE.md", Path(ROOT) / "CLAUDE.md"), ("main.py", Path(ROOT) / "server" / "main.py"),
                    ("javis_goal_plugin", Path(ROOT) / "system" / "plugins" / "javis-goal" / "plugin.py"),
                    ("javis_task_plugin", Path(ROOT) / "system" / "plugins" / "javis-task" / "plugin.py")):
        out[name] = _sha_file(p)[:16]
    return out


SETTLED_KINDS = ("goal.waiting_human", "goal.succeeded", "goal.blocked", "goal.guard", "goal.publish_conflict")


def settle_work(gid, revision, timeout=420):
    """Chờ revision này có kết cục (tin báo chờ người dùng, xong, bị chặn, xung đột CỦA ĐÚNG revision; hoặc một lượt việc
    nền của revision đã xong) VÀ mọi tin báo đã giao. Không dựa vào run_state: trạng thái chờ của revision trước còn
    nguyên tới khi revision mới được đánh giá. Bản tiếp nhận từ chat không có lượt việc nền nào."""
    def _done():
        rows = notices(gid)
        acts = [a for a in work_actions(gid, revision) if a["status"] != "running"]
        ended = any(r["kind"] in SETTLED_KINDS and r["revision"] == revision for r in rows)
        if not acts and not ended:
            return None
        return "done" if not [n for n in rows if not n["delivered"]] else None
    return wait_until(_done, timeout)


def adoption_check(stage, gid, revision, acts, ceiling_left):
    """Xem H.adoption_contract (review mã bàn giao, P2-2): làm lại vô ích bị bác, sửa vì chưa đạt được phép."""
    ass = [x for x in goal_store().assessments(P, gid) if int(x.get("revision") or 0) == int(revision)]
    rep["stages"][stage]["assessments"] = [{k: x.get(k) for k in ("verdict", "rationale")} for x in ass]
    rep["stages"][stage]["work_reasons"] = [(a.get("intent") or {}).get("last_verdict") for a in acts]
    ok, name = H.adoption_contract(acts, ceiling_left, APPROVED.get("aux") or {})
    return check(f"{stage} {name}", ok)


def adoption(gid, revision):
    """Sự kiện tiếp nhận bản chat của đúng revision (host đã đối chiếu biên nhận Write với bytes trên đĩa)."""
    return [e for e in goal_store().events(P, gid) if e.get("kind") == "artifact_adopted" and e.get("revision") == revision]


def receipt_brief(a):
    r = a.get("receipt") or {}
    return {k: r.get(k) for k in ("status", "error_code", "engine", "tool_calls_observed", "output_sha256", "usage")}


rep = {"mode": MODE, "scenario": "achieve_feedback_v1", "chat_limit": CHAT_LIMIT, "phase_ceiling": PHASE_CEILING,
       "max_calls": MAX_CALLS, "unit": "lượt engine cấp host (không phải số request nội bộ hay token)",
       "inputs": {"user_msg": USER_MSG, "user_msg_sha256": _sha_text(USER_MSG), "feedback_msg": FEEDBACK_MSG,
                  "feedback_msg_sha256": _sha_text(FEEDBACK_MSG), "deliverable": DELIV},
       "review_checklist": REVIEW_CHECKLIST, "stages": {}, "artifacts": {}, "simulated_acceptance": False}
t_start = time.time()
CLI = _resolve_cli() if MODE == "real" else ""
SRV = H.Server(root=ROOT, port=PORT, base=BASE, env0=ENV0, phase_ceiling=PHASE_CEILING, checks=CHECKS,
               cli=CLI)
g = None
sid = None
try:
    # ───────────── S0: server A (giai đoạn 1, nhịp dừng), cổng xác thực trước mọi tin chat ─────────────
    rep["stages"]["S0"] = {"start_s": start_server(1, tick_paused=True)}
    rep["routing_versions"] = _routing_versions()
    if MODE == "real":
        gate = auth_gate(CLI)
        rep["auth_gate"] = gate
        if not check("cổng xác thực: đúng binary engine dùng, gói thuê bao Anthropic gốc, settings không có đường "
                     f"API/đám mây ({gate.get('why') or 'đạt'})", gate["ok"]):
            raise Stop("S0: không chứng minh được chỉ dùng gói thuê bao, không gửi tin")
    check("S0 server thật lên được, WebSocket /ws nhận kết nối qua kiểm Origin", asyncio.run(ws_hello()) == "hello")

    # ───────────── S0b (A1): ba cửa của cổng trợ lý, KHÔNG gọi model ─────────────
    rep["stages"]["S0b"] = s0b = {}
    code, j = http("POST", "/sessions/new", data={"brain": "brain", "channel": f"agent:{AGENT_SLUG}"})
    sid = (j or {}).get("id")
    _ss = sess_store()
    # Phiên chat thường: trình duyệt tự cấp id, kho phiên tạo với kênh web (không qua /sessions/new).
    sid_plain = _ss.create_session(brain=KEY, engine="cli")
    check("S0b tạo được phiên trợ lý qua host (kênh agent:<slug>) và một phiên chat thường", bool(sid) and bool(sid_plain))
    m_plain = _ss.append_message(sid_plain, "user", USER_MSG)
    m_agent = _ss.append_message(sid, "user", USER_MSG)
    code, _b = http("POST", "/goal-requests", json={"message_ref": R.message_ref(sid_plain, m_plain)})
    s0b["plain_goal_request"] = code
    check("S0b chat thường: /goal-requests bị chặn (403), không gọi model", code == 403 and background_calls() == 0)
    code, _b = http("POST", "/goal-requests", json={"message_ref": R.message_ref(sid, m_agent)})
    s0b["agent_off_goal_request"] = code
    check("S0b trợ lý CHƯA bật: /goal-requests bị chặn (403), không gọi model", code == 403 and background_calls() == 0)
    code, j = http("POST", "/resonance/agents/toggle", json={"slug": AGENT_SLUG, "enabled": True, "session_id": sid})
    AG = (j or {}).get("agent") or {}
    s0b["toggle"] = {"code": code, "session": (j or {}).get("session"), "config_version": AG.get("config_version"),
                     "agent_key_hash": hashlib.sha256(str(AG.get("agent_key")).encode()).hexdigest()[:12]}
    check("S0b chủ dự án bật Cộng hưởng cho trợ lý qua API: cấp mã, phiên trợ lý dùng được (ready)",
          code == 200 and AG.get("enabled") is True and (j or {}).get("session") == "ready")
    code, j = http("GET", "/resonance/agents", params_extra={"slug": AGENT_SLUG, "session_id": sid})
    row = next((a for a in (j or {}).get("agents", []) if a.get("slug") == AGENT_SLUG), {})
    s0b["agents_row"] = {k: row.get(k) for k in ("enabled", "status", "support")}
    check("S0b danh sách trợ lý khớp kho: bật, active, và đọc lại trạng thái phiên vẫn ready",
          row.get("enabled") is True and row.get("status") == "active" and (j or {}).get("session") == "ready")
    if MODE == "real":
        sup = row.get("support") or {}
        check("S0b engine của trợ lý (bộ não chính đã duyệt) lập được mục tiêu và nhận bản chat",
              sup.get("goal") is True and sup.get("chat_output") is True, "contract")
    if MODE == "dry":
        # Dry: /goal-requests trên phiên trợ lý ĐÃ bật qua được cổng, tới bộ lập mục tiêu; engine bị chặn nên không
        # gọi model, không tạo mục tiêu (400). Real KHÔNG gọi đường này (bộ lập mục tiêu sẽ gọi model).
        code, _b = http("POST", "/goal-requests", json={"message_ref": R.message_ref(sid, m_agent)})
        s0b["agent_on_goal_request"] = code
        check("S0b dry: trợ lý đã bật: qua cổng, tới bộ lập mục tiêu, engine bị chặn nên 400, không gọi model",
              code == 400 and background_calls() == 0 and not all_goals())

    # ───────────── S1: lượt chat 1, bộ não tự quyết ─────────────
    kanban0 = kanban_tasks()
    if MODE == "real":
        sid1, turn = chat_turn("S1", USER_MSG, session_id=sid)
        rep["stages"]["S1"] = turn
        check("S1 lượt chat kết thúc (turn_done) trong ĐÚNG phiên trợ lý", sid1 == sid and turn["completed"])
    else:
        ss = sess_store()
        mid = ss.append_message(sid, "user", USER_MSG)
        _ag = goal_store().agent(KEY, AGENT_SLUG)
        prop = {"understanding": "Bản hướng dẫn nhận hàng cho nhân viên mới, sửa theo góp ý tới khi anh dùng được",
                "relevant_quote": "Em lo việc này giúp anh tới khi anh thấy dùng được thì thôi", "mode": "achieve",
                "stage": "delivery", "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"},
                "criteria": [{"description": "Bản hướng dẫn có mục Lỗi hay gặp", "evaluator": "artifact_contract",
                              "params": {"path": DELIV, "must_contain": ["Lỗi hay gặp"]}},
                             {"description": "Anh xác nhận bản hướng dẫn dùng được",
                              "evaluator": "human_confirmation"}]}
        asyncio.run(R.form_goal(R.message_ref(sid, mid), {
            "principal": P, "brain_root": KEY, "session_id": sid, "message_id": mid, "user_text": USER_MSG,
            "constraints": [], "budget_calls": 4, "proposal": prop,
            "agent_key": _ag["agent_key"], "agent_version": _ag["config_version"]},
            R.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=R.CallBudget(0), store=goal_store())))
        rep["stages"]["S1"] = {"dry": "mục tiêu lập bằng form_goal như tool javis_goal, gắn trợ lý của phiên"}
    rep["session_id_hash"] = hashlib.sha256(str(sid).encode()).hexdigest()[:12]
    rep["artifacts"]["after_S1"] = preserve("s1-chat")
    gs = [x for x in all_goals() if x.session_id == sid]
    new_tasks = kanban_tasks()[len(kanban0):]
    rep["routing"] = {"S1_goals": len(gs), "S1_kanban_tasks": new_tasks}
    if len(gs) != 1 or new_tasks:
        raise Stop(f"S1: bộ não lập {len(gs)} mục tiêu, giao {len(new_tasks)} việc Kanban; hợp đồng cần đúng một "
                   "mục tiêu và không giao Kanban (ghi nhận như kết quả pilot, không thử lại)")
    g = gs[0]
    rep["goal_S1"] = goal_view(g)
    check("S1 mục tiêu gắn đúng trợ lý của phiên (A1)",
          g.agent_key == (goal_store().agent(KEY, AGENT_SLUG) or {}).get("agent_key"), "contract")
    it = goal_store().get_intent(P, g.intent_id) or {}
    check("S1 ý định gốc trùng khớp toàn bộ lời người dùng của tin vừa gửi",
          str(it.get("text") or "").strip() == USER_MSG.strip())
    ok_kind = check("S1 mục tiêu kiểu achieve (đúng kiểu người dùng giao)", g.mode == "achieve", "contract")
    ok_path = check(f"S1 sản phẩm của mục tiêu đúng file người dùng nêu ({DELIV})", R._deliverable_rel(g) == DELIV,
                    "contract")
    ok_human = check("S1 có tiêu chí người dùng xác nhận (giữ việc mở tới khi anh thấy dùng được)",
                     any(c.get("evaluator") == "human_confirmation" for c in g.criteria), "contract")
    if not (ok_kind and ok_path and ok_human):
        raise Stop("S1: mục tiêu lệch hợp đồng kịch bản; các bước sau phụ thuộc kiểu, file và tiêu chí")
    if MODE == "real":
        check("S1 thẻ mục tiêu được đặt vào đúng phiên sau lượt, có biên nhận của host",
              bool(wait_until(lambda: [r for r in reports(sid) if r["goal_id"] == g.id and r["receipt"]], 20)))
    check("S1 nhịp tạm dừng: chưa có lượt việc nền", not work_actions(g.id) and background_calls() == 0)

    # ───────────── S2: giết A, dựng B (giai đoạn 1, nhịp chạy): bản đầu ─────────────
    SRV.kill()
    rep["stages"]["S2"] = {"start_s": start_server(1, tick_paused=False)}
    t0 = time.time()
    settle_work(g.id, g.revision)
    rep["stages"]["S2"]["work_s"] = round(time.time() - t0, 1)
    acts = work_actions(g.id, g.revision)
    rs = goal_store().run_state(P, g.id) or {}
    rep["stages"]["S2"].update({"receipts": [receipt_brief(a) for a in acts], "run_state": rs,
                                "notices": notices(g.id), "calls": background_calls()})
    if MODE == "real":
        ad1 = adoption(g.id, g.revision)
        rep["stages"]["S2"]["adopted"] = [e.get("payload") for e in ad1]
        if ad1:
            # Bộ não viết bản đầu trong lượt chat và host đã tiếp nhận. Trần là trần, không phải chỉ tiêu.
            check("S2 bản đầu tiếp nhận từ chat đúng một lần", len(ad1) == 1)
            adoption_check("S2", g.id, g.revision, acts, PHASE_CEILING[1])
        else:
            ok_r, why_r = H.work_receipt_ok(acts[-1]["receipt"] if acts else {}, APPROVED.get("aux") or {})
            check(f"S2 đúng một lượt việc nền làm bản đầu, receipt đúng hợp đồng ({why_r})", len(acts) == 1 and ok_r)
        pub = goal_store().published(P, g.id, DELIV) or {}
        rep["artifacts"]["draft1"] = {**preserve("draft1"), "revision": g.revision,
                                      "published_sha256": pub.get("sha256")}
        check("S2 bản đầu ở đúng file, bytes khớp hash host đã ghi khi đăng hay khi tiếp nhận",
              (BRAIN / DELIV).is_file() and bool(pub) and _sha_file(BRAIN / DELIV) == pub.get("sha256"))
        check("S2 bản đầu được lưu nguyên vẹn ra ngoài thư mục tạm (hash khớp)",
              rep["artifacts"]["draft1"].get("ok") is True)
        check("S2 sau bản đầu: chờ người dùng xác nhận", rs.get("run_state") == "waiting"
              and rs.get("block_reason") == "human_confirmation")
        ok_n, why_n = notice_in_session(sid, g.id, "goal.waiting_human", g.revision)
        rep["stages"]["S2"]["notice"] = why_n
        check(f"S2 tin báo BẢN ĐẦU (chờ xác nhận, revision {g.revision}) về đúng phiên, có biên nhận: {why_n}", ok_n)
    else:
        check("S2 dry: engine việc nền bị chặn trước khi gọi model", rs.get("run_state") == "blocked"
              and background_calls() == 0)
    calls_s2 = background_calls()
    check("S2 giai đoạn 1 tiêu tối đa 1 lượt việc nền", calls_s2 <= PHASE_CEILING[1])

    # ───────────── S3: giết B, dựng C (giai đoạn 1, nhịp chạy): trạng thái giữ, không báo lặp, không gọi thêm ──────
    SRV.kill()
    rep["stages"]["S3"] = {"start_s": start_server(1, tick_paused=False)}
    time.sleep(75)   # hơn hai nhịp lập lịch (30 giây)
    g3 = goal_store().get(P, g.id)
    keys = [r["report"] for r in reports(sid) if r["report"]]
    check("S3 sau dựng lại: mục tiêu, revision và trạng thái còn nguyên",
          g3 is not None and g3.revision == g.revision and g3.status == "active")
    check("S3 sau dựng lại: không có tin báo lặp", len(keys) == len(set(keys)))
    check("S3 lúc chờ người dùng: không gọi thêm model", background_calls() == calls_s2)
    if MODE == "real":
        check("S3 sản phẩm trên đĩa vẫn là bản đầu", _sha_file(BRAIN / DELIV) == rep["artifacts"]["draft1"]["sha256"])
    code, body = http("GET", f"/goals/{g.id}")
    check("S3 API thẻ trả trạng thái sống của mục tiêu", code == 200 and (body.get("goal") or {}).get("goal_id") == g.id)
    SRV.kill()
    rep["stages"]["S3"]["restart_D_s"] = start_server(1, tick_paused=True)

    # ───────────── S4: lượt chat 2 (góp ý) trên D, nhịp dừng ─────────────
    g_before = goal_store().get(P, g.id)
    kanban1 = kanban_tasks()
    if MODE == "real":
        sid2, turn = chat_turn("S4", FEEDBACK_MSG, session_id=sid)
        rep["stages"]["S4"] = turn
        check("S4 lượt chat kết thúc trong CÙNG phiên", sid2 == sid and turn["completed"])
    else:
        ss = sess_store()
        mid2 = ss.append_message(sid, "user", FEEDBACK_MSG)
        try:
            R.revise_goal(goal_store(), P, g.id, g_before.revision,
                          {"constraints": ["Bước đối chiếu phiếu giao có một ví dụ cụ thể",
                                           "Có bước chụp ảnh hàng hỏng trước khi ký"],
                           "relevant_quote": "em thêm một ví dụ cụ thể"},
                          {"message_ref": R.message_ref(sid, mid2), "session_id": sid, "message_id": mid2,
                           "user_text": FEEDBACK_MSG, "constraints": [], "user_unsure": False,
                           "reason": "góp ý của người dùng", "agent_key": g.agent_key,
                           "agent_version": (goal_store().agent(KEY, AGENT_SLUG) or {}).get("config_version")})
        except Exception as e:  # noqa: BLE001
            check(f"S4 dry: revise_goal nhận góp ý ({type(e).__name__}: {e})", False)
        rep["stages"]["S4"] = {"dry": "góp ý nối bằng revise_goal như javis_goal op=update"}
    g4 = goal_store().get(P, g.id)
    gs4 = [x for x in all_goals() if x.session_id == sid]
    new_tasks = kanban_tasks()[len(kanban1):]
    rep["routing"].update({"S4_goals": len(gs4), "S4_kanban_tasks": new_tasks,
                           "S4_revision": [g_before.revision, g4.revision]})
    rep["artifacts"]["after_S4"] = preserve("s4-chat")
    if len(gs4) != 1 or new_tasks or g4.revision != g_before.revision + 1:
        raise Stop(f"S4: góp ý không nối vào mục tiêu đang mở (mục tiêu {len(gs4)}, Kanban {len(new_tasks)}, revision "
                   f"{g_before.revision}->{g4.revision}); ghi nhận, không thử lại")
    rep["goal_S4"] = goal_view(g4)
    it4 = goal_store().get_intent(P, g4.intent_id) or {}
    check("S4 ý định mới là đúng lời góp ý và nối về ý định trước",
          str(it4.get("text") or "").strip() == FEEDBACK_MSG.strip()
          and it4.get("prev_intent_id") == g_before.intent_id)
    check("S4 giữ ràng buộc cũ, đường dẫn sản phẩm và tiêu chí người dùng xác nhận",
          set(g_before.constraints) <= set(g4.constraints) and R._deliverable_rel(g4) == DELIV
          and any(c.get("evaluator") == "human_confirmation" for c in g4.criteria), "contract")
    check("S4 có lịch làm lại cho revision mới, chưa ai nhận (nhịp dừng)",
          any(w["kind"] == "work" for w in goal_store().wakes(P, g.id)) and not work_actions(g.id, g4.revision))
    check("S4 lượt chat không tiêu lượt việc nền", background_calls() == calls_s2)

    # ───────────── S5: giết D, dựng E (giai đoạn 2, nhịp chạy, trần tích luỹ 2): bản sửa ─────────────
    SRV.kill()
    rep["stages"]["S5"] = {"start_s": start_server(2, tick_paused=False)}
    t0 = time.time()
    settle_work(g.id, g4.revision)
    rep["stages"]["S5"]["work_s"] = round(time.time() - t0, 1)
    acts5 = work_actions(g.id, g4.revision)
    rs5 = goal_store().run_state(P, g.id) or {}
    rep["stages"]["S5"].update({"receipts": [receipt_brief(a) for a in acts5], "run_state": rs5,
                                "notices": notices(g.id), "calls": background_calls()})
    if MODE == "real":
        ad2 = adoption(g.id, g4.revision)
        rep["stages"]["S5"]["adopted"] = [e.get("payload") for e in ad2]
        if ad2:
            check("S5 bản sửa tiếp nhận từ chat (lượt góp ý tự Write) đúng một lần", len(ad2) == 1)
            adoption_check("S5", g.id, g4.revision, acts5, PHASE_CEILING[2] - calls_s2)
        else:
            ok_r, why_r = H.work_receipt_ok(acts5[-1]["receipt"] if acts5 else {}, APPROVED.get("aux") or {})
            check(f"S5 đúng một lượt bản sửa cho revision mới, receipt đúng hợp đồng ({why_r})",
                  len(acts5) == 1 and ok_r)
        pub = goal_store().published(P, g.id, DELIV) or {}
        rep["artifacts"]["draft2"] = {**preserve("draft2"), "revision": g4.revision,
                                      "published_sha256": pub.get("sha256"), "feedback_sha256": _sha_text(FEEDBACK_MSG)}
        check("S5 bản sửa đã đăng: bytes khớp hash host, khác bản đầu",
              _sha_file(BRAIN / DELIV) == pub.get("sha256")
              and _sha_file(BRAIN / DELIV) != rep["artifacts"]["draft1"]["sha256"])
        check("S5 bản sửa được lưu nguyên vẹn (hash khớp)", rep["artifacts"]["draft2"].get("ok") is True)
        check("S5 sau bản sửa: chờ người dùng xác nhận", rs5.get("block_reason") == "human_confirmation")
        # Tin của BẢN SỬA: đúng loại và đúng revision mới; tin bản đầu (revision cũ) hay thẻ reframe không tính.
        ok_n, why_n = notice_in_session(sid, g.id, "goal.waiting_human", g4.revision)
        rep["stages"]["S5"]["notice"] = why_n
        check(f"S5 tin báo BẢN SỬA (revision {g4.revision}) về đúng phiên, có biên nhận: {why_n}", ok_n)
        keys = [r["report"] for r in reports(sid) if r["report"]]
        check("S5 không có tin báo lặp trong phiên", bool(keys) and len(keys) == len(set(keys)))
    else:
        check("S5 dry: engine việc nền vẫn bị chặn, không gọi model", background_calls() == 0)
    check("S5 tổng lượt việc nền không vượt trần giai đoạn 2", background_calls() <= PHASE_CEILING[2])
    calls_s5 = background_calls()
    time.sleep(75)
    check("S5 lúc chờ người dùng: không gọi thêm", background_calls() == calls_s5)

    # ───────────── S6: xác nhận từng tiêu chí người dùng của revision hiện hành (MÔ PHỎNG) ─────────────
    code, body = http("GET", f"/goals/{g.id}")
    v = body.get("goal") or {}
    human = [c for c in v.get("criteria", []) if c.get("evaluator") == "human_confirmation"]
    rep["stages"]["S6"] = {"human_criteria": [c.get("id") for c in human], "artifact_ref": v.get("artifact_ref"),
                           "revision": v.get("revision")}
    if MODE == "real":
        rep["simulated_acceptance"] = True
        check("S6 có sản phẩm của revision hiện hành để xác nhận", bool(v.get("artifact_ref"))
              and v.get("revision") == g4.revision)
        check("S6 có ít nhất một tiêu chí người dùng xác nhận", bool(human))
        for c in human:
            code, _b = H.accept(CHECKS, http, g.id, v, c)     # qua cổng: kiểm nào hỏng trước đó thì không bấm
            check(f"S6 bấm Đạt yêu cầu cho tiêu chí {c['id']} qua API (mô phỏng): 200", code == 200)
        ok_s = wait_until(lambda: goal_store().get(P, g.id).status == "succeeded"
                          and notice_in_session(sid, g.id, "goal.succeeded", v["revision"])[0], 120)
        why_s = notice_in_session(sid, g.id, "goal.succeeded", v["revision"])[1]
        rep["stages"]["S6"]["notice"] = why_s
        check(f"S6 mục tiêu đạt và tin THÀNH CÔNG về đúng phiên, có biên nhận ({why_s}); đường API, KHÔNG phải "
              "nghiệm thu nội dung", bool(ok_s))
    else:
        code, _b = http("POST", f"/goals/{g.id}/feedback",
                        json={"kind": "goal_fit_confirmed", "expected_revision": v.get("revision", 1)})
        check("S6 dry: POST feedback qua kiểm Origin của server thật: 200", code == 200)
        code, _b = http("POST", f"/goals/{g.id}/commands", json={"command": "pause",
                                                                 "expected_revision": v.get("revision", 1)})
        check("S6 dry: lệnh tạm dừng vẫn có hiệu lực", code == 200 and goal_store().get(P, g.id).paused)
    check("S6 xác nhận không gọi thêm model", background_calls() == calls_s5)
except Stop as e:
    print(f"DỪNG: {e}")
    rep["stopped"] = str(e)
except H.GateClosed as e:
    # Cổng chi phí đóng: hoặc đã có kiểm hỏng (kết luận theo kiểm đó), hoặc hết lượt/lượt chat lỗi (lỗi kỹ thuật).
    print(f"DỪNG (cổng chi phí): {e}")
    rep["stopped"] = str(e)
    if not CHECKS.failures():
        check(f"lượt chat hoàn tất trong hạn mức ({e})", False)
except Exception as e:  # noqa: BLE001
    check(f"bộ chạy không lỗi ({type(e).__name__}: {e})", False)
finally:
    SRV.kill()
    rep["artifacts"]["final"] = preserve("final") if not rep["artifacts"].get("draft2") else rep["artifacts"]["draft2"]
    if g is not None:
        try:
            gf = goal_store().get(P, g.id)
            rep["goal_final"] = goal_view(gf)
            rep["notices_final"] = notices(g.id)
        except Exception:  # noqa: BLE001
            pass
        try:
            rep["work_outputs"], _work_saved = preserve_work_outputs(g.id)
        except Exception as e:  # noqa: BLE001
            rep["work_outputs"], _work_saved = {"error": f"{type(e).__name__}: {e}"}, False
        if not _work_saved:
            # Không lưu được bản duy nhất của một lượt việc nền thì KHÔNG dọn sandbox: báo rõ chỗ còn giữ.
            os.environ["JAVIS_RESONANCE_E2E_KEEP"] = "1"
            print("CẢNH BÁO: chưa lưu được đầu ra việc nền; giữ nguyên sandbox để lấy lại bằng tay.")
    rep["host_engine_turns"] = {"chat": TURNS.used(), "chat_ledger": TURNS.entries(), "background": background_calls(),
                                "total": TURNS.used() + background_calls()}
    check(f"tổng lượt engine cấp host trong trần {MAX_CALLS} (chat {CHAT_LIMIT}, việc nền {PHASE_CEILING[2]})",
          TURNS.used() <= CHAT_LIMIT and background_calls() <= PHASE_CEILING[2])
    rep["servers"] = SRV.started
    rep["seconds_total"] = round(time.time() - t_start, 1)
    # Kết luận: dừng theo hợp đồng KHÁC lỗi kỹ thuật KHÁC lệch hợp đồng. Kỹ thuật đạt thì nội dung CHỜ người review.
    rep["acceptance"] = ("technical_failed" if _fails else "contract_failed" if _contract else
                         "stopped" if rep.get("stopped") else
                         "pending_content_review" if MODE == "real" else "dry_ok")
    rep["content_review"] = "pending" if rep["acceptance"] == "pending_content_review" else "not_applicable"
    rep["checks"] = _log
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True,
                              timeout=10).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "server", "system"], cwd=str(ROOT),
                                    capture_output=True, text=True, timeout=10).stdout.strip())
    except Exception:  # noqa: BLE001
        head, dirty = "", None
    rep["commit"], rep["server_dirty"] = head, dirty
    print("E2E_REPORT " + json.dumps({k: rep[k] for k in ("mode", "acceptance", "host_engine_turns", "seconds_total")
                                      if k in rep}, ensure_ascii=False))
    if OUT:
        txt = json.dumps(rep, ensure_ascii=True, indent=2) + "\n"
        for secret_path in (str(BASE), str(Path.home())):
            txt = txt.replace(json.dumps(secret_path)[1:-1], "<path>")
        Path(OUT).write_text(txt, encoding="utf-8", newline="\n")
    if not os.environ.get("JAVIS_RESONANCE_E2E_KEEP"):
        shutil.rmtree(BASE, ignore_errors=True)

if rep.get("acceptance") == "pending_content_review":
    print("\nOK (kỹ thuật): mọi kiểm kỹ thuật đạt. Nội dung CHỜ người review trên hai bản đã lưu; CHƯA nghiệm thu pilot.")
    sys.exit(0)
if rep.get("acceptance") != "dry_ok":
    print(f"\n{rep.get('acceptance')}: {len(_fails)} lỗi kỹ thuật, {len(_contract)} lệch hợp đồng", _fails + _contract)
    sys.exit(1)
print("\nOK")
