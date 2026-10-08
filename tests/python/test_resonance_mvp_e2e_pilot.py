"""Resonance MVP: pilot đầu-cuối qua ĐƯỜNG CHAT THẬT (nghiệm thu điều kiện "đi hết vòng trên host thật").

    JAVIS_RESONANCE_E2E=dry  python tests/python/test_resonance_mvp_e2e_pilot.py      # KHÔNG gọi model
    JAVIS_RESONANCE_E2E=real JAVIS_RESONANCE_PILOT_SETTINGS=<settings.json thật> \\
        python tests/python/test_resonance_mvp_e2e_pilot.py                            # gọi model, cần người dùng duyệt

Không đặt JAVIS_RESONANCE_E2E thì bỏ qua (CI và tests/run.py không gọi gì). Kịch bản, hạn mức và kết quả các lần
chạy ở docs/dev/resonance-mvp-e2e-pilot-plan.md.

Bộ chạy dựng server Javis THẬT từ checkout này (tiến trình riêng, cổng 7791), JAVIS_STATE_DIR và BRAINS_DIR tạm,
brain mặc định ("Brain Default", dashboard gọi tắt là "brain") bật Resonance, dữ liệu mô phỏng.

An toàn chi phí (review e2e P1-1, P1-2), kiểm TRƯỚC khi gửi tin:
- Chỉ chép các ô chọn engine; settings sandbox không có khoá hay chế độ API key nào.
- Môi trường server đã lọc (_e2e_pilot_guard.clean_env); binary `claude` được ghim (JAVIS_CLAUDE_CLI) đúng binary mà
  engine dùng; `claude auth status` chạy bằng chính binary, cwd và môi trường đó phải là gói thuê bao Anthropic gốc;
  các nguồn settings Claude Code engine nạp (user, project, local, managed) không có apiKeyHelper hay env chọn nhà
  cung cấp. Không chứng minh được thì DỪNG, không gửi tin.
- Trần tổng JAVIS_RESONANCE_E2E_MAX_CALLS (mặc định 3) lượt engine cấp host: lượt bộ não tính trước khi gửi, phần còn
  lại server chặn TRƯỚC lượt gọi vượt trần (JAVIS_RESONANCE_CALL_CEILING, sổ bền trong SQLite, truyền cho mọi tiến
  trình server). Một lượt bộ não có thể gồm nhiều request nội bộ của SDK: đây không phải số request hay token.

Kịch bản (real), mọi điều kiện nghiệm thu là lỗi CỨNG (review e2e P2-1):
1. Server A (nhịp Resonance TẠM DỪNG: JAVIS_RESONANCE_TICK_PAUSED=1) nhận MỘT tin chat qua /ws như dashboard.
   Bộ não tự quyết có gọi javis_goal hay không. Không lập mục tiêu: ghi kết quả và DỪNG.
2. GIẾT cả cây tiến trình A (chắc chắn chưa có lượt việc nền), dựng B (nhịp chạy): nhịp lập lịch tự làm lượt việc nền,
   đăng sản phẩm (hash file trên đĩa khớp hash host đã ghi), báo về đúng phiên có biên nhận.
3. GIẾT B, dựng C: không báo lặp, không gọi thêm.
4. Có tiêu chí người dùng duyệt thì bấm "Đạt yêu cầu" qua API như nút trên thẻ (bắt buộc có sản phẩm để duyệt).
5. Kết thúc theo kiểu mục tiêu: achieve phải succeeded và có tin báo thành công; maintain phải có đánh giá met, tin
   báo goal.maintained, lịch xem lại có giới hạn; rồi người dùng TẠM DỪNG qua API để không còn việc nền nào.
dry: không gửi tin chat, không gọi model; vẫn chạy cổng xác thực (không gọi model), lập mục tiêu bằng đúng hàm tool
javis_goal dùng, engine việc nền bị chặn; kiểm hạ tầng dựng/giết/khởi động lại, báo cáo, API thẻ.
JAVIS_RESONANCE_E2E_OUT: nơi ghi báo cáo JSON (không có đường dẫn cá nhân, không email, không token).
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

sys.path.insert(0, str(Path(__file__).parent))
import _e2e_pilot_guard as G  # noqa: E402

PORT = int(os.environ.get("JAVIS_RESONANCE_E2E_PORT", "7791"))
MAX_CALLS = int(os.environ.get("JAVIS_RESONANCE_E2E_MAX_CALLS", "3"))
BRAIN_TURNS_PLANNED = 1 if MODE == "real" else 0
CEILING = MAX_CALLS - BRAIN_TURNS_PLANNED
if CEILING < 0:
    print("FAIL pilot: trần nhỏ hơn số lượt bộ não đã định")
    sys.exit(1)
# Đường dẫn NGẮN: đường dẫn sâu làm ghi đầu ra lỗi write_failed trên Windows (MAX_PATH, ghi nhận ở M4).
BASE = Path(tempfile.mkdtemp(prefix="rse2e-", dir=os.environ.get("TEMP") or None)).resolve()
STATE, BRAINS = BASE / "state", BASE / "brains"
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
    # Bộ chọn chỉ chữ của Resonance chặn provider này: việc nền không gọi model nào.
    MODEL = {"auxiliary": {"provider": "grok-cli", "model": "grok-dry"}}
assert not any(k in MODEL for k in ("claude_auth", "anthropic_api_key")), "settings sandbox không được có chế độ API key"
(STATE / "settings.json").write_text(json.dumps({"model": MODEL}, ensure_ascii=False), encoding="utf-8", newline="\n")

os.environ["JAVIS_STATE_DIR"] = str(STATE)
import resonance as R  # noqa: E402  - sau khi đặt JAVIS_STATE_DIR
import resonance_store as RS  # noqa: E402
import sessions as SS  # noqa: E402

KEY = str(BRAIN.resolve())
P = RS.Principal("agent", "javis", KEY)
ORIGIN = f"http://127.0.0.1:{PORT}"
# Lời giao loại DUY TRÌ (đúng nhóm javis_goal theo luật hiện hành), dữ liệu mô phỏng, không nêu tên công cụ.
OUT = os.environ.get("JAVIS_RESONANCE_E2E_OUT", "")
if MODE == "real" and not OUT:
    print("FAIL pilot: chế độ real cần JAVIS_RESONANCE_E2E_OUT (báo cáo và bản lưu sản phẩm cho người review)")
    sys.exit(1)
USER_MSG = ("(Dữ liệu mô phỏng để thử nghiệm.) Từ giờ duy trì giúp mình ghi chú Inbox/viec-dang-do.md: lúc nào cũng "
            "liệt kê đủ các việc đang dở bên dưới, mỗi việc ghi người phụ trách và hạn chót. Khi mình báo thêm việc "
            "thì cập nhật vào, có bản mới thì báo mình xem. Đừng đụng tới Notes/ghi-chu-cu.md.\n"
            "Việc đang dở: Lan soạn kế hoạch bài viết tháng 11, hạn 09/10. Minh kiểm lại lịch đăng, hạn 10/10. "
            "Hà gửi bảng số liệu cho cả nhóm, hạn 12/10.")

# Hợp đồng kỳ vọng ĐỘC LẬP của kịch bản cố định (review e2e vòng 2, P2-2): chấm trên file thật theo lời người dùng,
# không lấy tiêu chí hay kiểu mục tiêu do bộ não đề xuất làm đáp án. Không đưa thêm gì vào prompt.
SCENARIO = {"mode": "maintain", "path": "Inbox/viec-dang-do.md",
            "triples": [("Lan", "09/10"), ("Minh", "10/10"), ("Hà", "12/10")],
            # Ba bộ VIỆC, NGƯỜI, HẠN (review e2e vòng 3): chấm trong cùng một đơn vị trình bày; cụm đặc trưng của từng
            # việc kèm vài cách nói đồng nghĩa. Không khớp cụm nào thì "chưa xác minh", không tính là đạt.
            "items": [{"who": "Lan", "when": "09/10", "task": "soạn kế hoạch bài viết tháng 11",
                       "task_keys": [["kế hoạch", "bài viết"], ["kế hoạch", "tháng 11"], ["kế hoạch nội dung"]]},
                      {"who": "Minh", "when": "10/10", "task": "kiểm lại lịch đăng",
                       "task_keys": [["lịch đăng"], ["lịch", "đăng bài"]]},
                      {"who": "Hà", "when": "12/10", "task": "gửi bảng số liệu cho cả nhóm",
                       "task_keys": [["số liệu"]]}]}
# Cấu hình engine người dùng đã duyệt cho lần chạy (review e2e vòng 2, P2-1). Ghi đè được bằng JSON trong
# JAVIS_RESONANCE_E2E_APPROVED; dry cố ý chọn provider việc nền bị chặn và không chạy bộ não.
APPROVED = (json.loads(os.environ["JAVIS_RESONANCE_E2E_APPROVED"]) if os.environ.get("JAVIS_RESONANCE_E2E_APPROVED")
            else {"main": {"provider": "anthropic-cli", "model": "claude-opus-5-5"},
                  "aux": {"provider": "anthropic-cli", "model": "sonnet"}, "claude_model": "claude-opus-5-5"}
            if MODE == "real" else {"aux": {"provider": "grok-cli"}})
BG_CWD = STATE / "resonance_cwd"     # cwd của lượt việc nền (main._reply_policy_sandbox_engine, cwd_name)
BG_CWD.mkdir(parents=True, exist_ok=True)
PILOT_VARS = ("JAVIS_RESONANCE_TICK_PAUSED", "JAVIS_RESONANCE_CALL_CEILING", "JAVIS_CLAUDE_CLI", "JAVIS_CLAUDE_BIN",
              "JAVIS_STATE_DIR", "BRAINS_DIR", "JAVIS_PORT")

_fails, _log = [], []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    _log.append({"check": name, "ok": bool(cond)})
    if not cond:
        _fails.append(name)
    return bool(cond)


# Bỏ cả các biến của chính pilot có thể thừa kế từ shell cha: mỗi tiến trình server chỉ có đúng giá trị bộ chạy đặt.
ENV0 = {k: v for k, v in G.clean_env(dict(os.environ)).items() if k not in PILOT_VARS}


def resolve_engines() -> dict:
    """Engine runtime SẼ chạy, resolve bằng chính luật runtime (aux_engine.main_spec, read_spec) trên settings sandbox,
    trong môi trường đã lọc. Không gọi engine."""
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
    """Binary `claude` theo đúng cách engine chọn (claude_cli.tim_binary), chạy trong môi trường đã lọc."""
    cp = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, 'server'); "
                         "from claude_cli import tim_binary; print(tim_binary('claude') or '')"],
                        cwd=str(ROOT), env=ENV0, capture_output=True, text=True, timeout=60)
    return (cp.stdout or "").strip().splitlines()[-1] if (cp.stdout or "").strip() else ""


def _auth_at(cli: str, cwd: Path) -> tuple:
    st = subprocess.run([cli, "auth", "status", "--json"], cwd=str(cwd), env=ENV0, capture_output=True, text=True,
                        timeout=60)
    return json.loads(st.stdout or "{}")


def auth_gate(cli: str) -> dict:
    """Cổng an toàn, không gọi model (review e2e P1-2 và vòng 2):
    1. engine runtime sẽ chạy (bộ não chính, việc nền) đúng cấu hình người dùng đã duyệt;
    2. `claude auth status` bằng ĐÚNG binary engine dùng, ở CẢ HAI cwd (lượt chat: brain; lượt việc nền:
       resonance_cwd), môi trường đã lọc: gói thuê bao Anthropic gốc;
    3. nguồn settings người dùng/dự án của cả hai cwd không có apiKeyHelper hay env chọn khoá/nhà cung cấp;
    4. không có nguồn settings do quản trị đặt (managed, managed-settings.d, registry policy, cache): có thì môi trường
       CHƯA hỗ trợ, dừng.
    Hook, plugin, MCP trong settings được GHI TÊN là ngoài phạm vi bảo đảm (cổng chứng minh xác thực của Claude, không
    chứng minh mọi tiến trình con không tiêu tiền)."""
    out = {"cli_found": bool(cli), "ok": False, "why": ""}
    eng = resolve_engines()
    out["engines"] = eng
    out["approved"] = APPROVED
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


class Server:
    """Server Javis thật của checkout này. kill() giết CẢ CÂY tiến trình (mô phỏng sập máy, không tắt êm)."""

    def __init__(self, cli: str):
        self.n, self.proc, self.cli, self.started = 0, None, cli, []

    def start(self, tick_paused=False, wait_s=120):
        self.n += 1
        env = {**ENV0, "JAVIS_PORT": str(PORT), "JAVIS_STATE_DIR": str(STATE), "BRAINS_DIR": str(BRAINS),
               "JAVIS_REQUIRE_LOGIN": "0", "PYTHONUTF8": "1", "JAVIS_RESONANCE_CALL_CEILING": str(CEILING)}
        if self.cli:
            env["JAVIS_CLAUDE_CLI"] = self.cli
        if tick_paused:
            env["JAVIS_RESONANCE_TICK_PAUSED"] = "1"
        # Trạng thái hiệu lực của từng tiến trình, để không nhầm "nhịp hỏng" với "nhịp đang tạm dừng".
        self.started.append({"n": self.n, "tick_paused": env.get("JAVIS_RESONANCE_TICK_PAUSED") == "1",
                             "call_ceiling": env.get("JAVIS_RESONANCE_CALL_CEILING"),
                             "cli_pinned": bool(env.get("JAVIS_CLAUDE_CLI"))})
        log = open(BASE / f"server-{self.n}.log", "w", encoding="utf-8")
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self.proc = subprocess.Popen([sys.executable, "server/main.py"], cwd=str(ROOT), env=env, stdout=log,
                                     stderr=subprocess.STDOUT, creationflags=flags)
        import httpx
        t0 = time.time()
        while time.time() - t0 < wait_s:
            if self.proc.poll() is not None:
                raise RuntimeError(f"server thoát sớm, xem server-{self.n}.log")
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


def background_calls():
    import sqlite3
    db = STATE / "resonance.sqlite3"
    if not db.exists():
        return 0
    c = sqlite3.connect(str(db))
    n = int(c.execute("SELECT COALESCE(SUM(calls_used),0) FROM goals").fetchone()[0])
    try:
        n += int(c.execute("SELECT COUNT(*) FROM call_ledger WHERE status='used'").fetchone()[0])
    except Exception:  # noqa: BLE001
        pass
    c.close()
    return n


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


def notices(goal_id):
    import sqlite3
    c = sqlite3.connect(str(STATE / "resonance.sqlite3"))
    rows = c.execute("SELECT id, kind, delivered_at FROM outbox WHERE goal_id=? ORDER BY id", (goal_id,)).fetchall()
    c.close()
    return [{"id": r[0], "kind": r[1], "delivered": r[2] is not None} for r in rows]


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


def _cut(v, n=3000):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + f"...(+{len(s) - n})"


async def ws_chat(message, timeout=900):
    """Gửi MỘT tin như dashboard, đọc khung tới turn_done. Trả (session_id, loại khung, khung công cụ, câu trả lời)."""
    import websockets
    frames, tools, answer, sid = [], [], [], None
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws", origin=ORIGIN, max_size=None) as ws:
        await asyncio.wait_for(ws.recv(), 20)
        await ws.send(json.dumps({"message": message, "brain": "brain"}))
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
                break
    return sid, frames, tools, "".join(answer)[-6000:]


def http(method, path, **kw):
    import httpx
    r = httpx.request(method, f"{ORIGIN}{path}", params={"brain": "brain"}, headers={"Origin": ORIGIN}, timeout=30,
                      **kw)
    try:
        return r.status_code, r.json()
    except Exception:  # noqa: BLE001
        return r.status_code, {}


def _sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest() if p and Path(p).is_file() else ""


def _routing_versions():
    out = {}
    for name, p in (("repo_CLAUDE.md", Path(ROOT) / "CLAUDE.md"), ("brain_CLAUDE.md", BRAIN / "CLAUDE.md"),
                    ("javis_goal_plugin", Path(ROOT) / "system" / "plugins" / "javis-goal" / "plugin.py")):
        out[name] = _sha_file(p)[:16]
    return out


rep = {"mode": MODE, "max_calls": MAX_CALLS, "brain_turns_planned": BRAIN_TURNS_PLANNED,
       "background_ceiling": CEILING, "unit": "lượt engine cấp host (không phải số request nội bộ hay token)",
       "steps": {}}
brain_turns = 0
t_start = time.time()
CLI = _resolve_cli()
SRV = Server(CLI)
try:
    # ───────────── Bước 0: cổng xác thực, TRƯỚC mọi tin chat (không gọi model) ─────────────
    rep["steps"]["start_A_s"] = round(SRV.start(tick_paused=True), 1)
    gate = auth_gate(CLI)
    rep["auth_gate"] = gate
    rep["routing_versions"] = _routing_versions()
    if not check("cổng xác thực: đúng binary engine dùng, gói thuê bao Anthropic gốc, settings không có đường "
                 f"API/đám mây ({gate.get('why') or 'đạt'})", gate["ok"]):
        raise SystemExit("dừng trước khi gửi tin: không chứng minh được chỉ dùng gói thuê bao")
    check("server thật lên được, WebSocket /ws nhận kết nối qua kiểm Origin", asyncio.run(ws_hello()) == "hello")

    # ───────────── Bước 1: tin chat (real) hoặc lập mục tiêu bằng đúng hàm của tool (dry) ─────────────
    if MODE == "real":
        if brain_turns + 1 + CEILING > MAX_CALLS:
            raise SystemExit("dừng: lượt bộ não cộng trần việc nền vượt trần đã duyệt")
        brain_turns = 1          # tính TRƯỚC khi gửi: lượt bộ não được giữ chỗ trong trần
        t0 = time.time()
        sid, frames, tools, answer = asyncio.run(ws_chat(USER_MSG))
        rep["steps"]["chat_turn_s"] = round(time.time() - t0, 1)
        rep["frames"] = {k: frames.count(k) for k in sorted(set(f for f in frames if f))}
        rep["tool_frames"] = tools
        rep["final_answer"] = answer
        check("lượt chat kết thúc (turn_done) và có session_id", bool(sid) and frames and frames[-1] == "turn_done")
    else:
        ss = sess_store()
        sid = ss.get_or_create(None, brain=KEY, engine="dry", model="dry")
        mid = ss.append_message(sid, "user", USER_MSG)
        prop = {"understanding": "Duy trì ghi chú việc đang dở, mỗi việc có người phụ trách và hạn",
                "relevant_quote": "duy trì giúp mình ghi chú", "mode": "maintain", "stage": "delivery",
                "horizon": {"kind": "maintain"},
                "criteria": [{"description": "Ghi chú có đủ ba người", "evaluator": "artifact_contract",
                              "params": {"path": "Inbox/viec-dang-do.md", "must_contain": ["Lan", "Minh", "Hà"]}}]}
        asyncio.run(R.form_goal(R.message_ref(sid, mid), {
            "principal": P, "brain_root": KEY, "session_id": sid, "message_id": mid, "user_text": USER_MSG,
            "constraints": [], "budget_calls": 3, "proposal": prop},
            R.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=R.CallBudget(0), store=goal_store())))
    rep["session_id_hash"] = hashlib.sha256(str(sid).encode()).hexdigest()[:12]
    gs = [g for g in _all_goals() if g.session_id == sid]
    rep["goal_created"] = bool(gs)
    try:
        import sqlite3
        kc = sqlite3.connect(str(STATE / "kanban.sqlite3"))
        rep["kanban_tasks"] = [{"title": r[0], "intent": _cut(r[1], 1500), "status": r[2]} for r in
                               kc.execute("SELECT title, intent, status FROM tasks").fetchall()]
        kc.close()
    except Exception:  # noqa: BLE001
        rep["kanban_tasks"] = []
    if not check("bộ não tự lập ĐÚNG MỘT mục tiêu qua javis_goal, gắn đúng phiên chat" if MODE == "real"
                 else "mục tiêu lập bằng form_goal, gắn đúng phiên", len(gs) == 1):
        raise SystemExit("dừng: không có mục tiêu để theo dõi (ghi nhận như kết quả pilot, không thử lại)")
    g = gs[0]
    rep["goal"] = {"understanding": g.understanding, "stage": g.stage, "mode": g.mode, "horizon": g.horizon,
                   "criteria": [{k: c.get(k) for k in ("id", "evaluator", "description", "params")} for c in g.criteria],
                   "guards": [x.get("description") for x in g.guards], "constraints": list(g.constraints),
                   "budget_calls": g.budget_calls}
    if MODE == "real":
        check(f"mục tiêu đúng KIỂU người dùng giao ({SCENARIO['mode']}), không phải kiểu bộ não tự chọn khác",
              g.mode == SCENARIO["mode"])
        check(f"sản phẩm của mục tiêu đúng file người dùng nêu ({SCENARIO['path']})",
              R._deliverable_rel(g) == SCENARIO["path"])
    it = goal_store().get_intent(P, g.intent_id) or {}
    check("ý định gốc TRÙNG KHỚP toàn bộ lời người dùng của tin vừa gửi",
          str(it.get("text") or "").strip() == USER_MSG.strip())
    if MODE == "real":
        check("thẻ mục tiêu được đặt vào đúng phiên sau lượt, có biên nhận của host",
              bool(wait_until(lambda: [r for r in reports(sid) if r["goal_id"] == g.id and r["receipt"]], 20)))
    check("server A tạm dừng nhịp: chưa có lượt việc nền nào trước khi bị giết",
          not [a for a in goal_store().actions(P, g.id) if a["kind"] == "work"] and background_calls() == 0)

    # ───────────── Bước 2: GIẾT A (gián đoạn), dựng B với nhịp chạy; scheduler phải tự làm tiếp ─────────────
    SRV.kill()
    rep["steps"]["start_B_s"] = round(SRV.start(), 1)

    def _settled():
        acts = [a for a in goal_store().actions(P, g.id) if a["kind"] == "work" and a["status"] != "running"]
        if not acts:
            return None
        return "done" if not [n for n in notices(g.id) if not n["delivered"]] else None

    t0 = time.time()
    wait_until(_settled, 300)
    rep["steps"]["work_after_restart_s"] = round(time.time() - t0, 1)
    acts = [a for a in goal_store().actions(P, g.id) if a["kind"] == "work"]
    check("sau khởi động lại, nhịp lập lịch tự làm lượt việc nền (không cần ai gọi lại)", bool(acts))
    cur = goal_store().get(P, g.id)
    rs = goal_store().run_state(P, g.id) or {}
    rep["after_work"] = {"run_state": rs.get("run_state"), "block_reason": rs.get("block_reason"), "status": cur.status,
                         "receipts": [{k: (a["receipt"] or {}).get(k) for k in
                                       ("status", "error_code", "engine", "tool_calls_observed", "output_sha256",
                                        "usage")} for a in acts],
                         "assessments": [{k: x.get(k) for k in ("revision", "verdict", "rationale")}
                                         for x in goal_store().assessments(P, g.id)][-4:],
                         "notices": notices(g.id)}
    if MODE == "real":
        w = acts[-1]["receipt"] if acts else {}
        check("lượt việc nền: receipt succeeded, đúng provider đã chọn, không gọi công cụ",
              w.get("status") == "succeeded" and w.get("engine", {}).get("provider") ==
              w.get("engine", {}).get("requested_provider") and w.get("tool_calls_observed") == 0)
        deliv = SCENARIO["path"]          # đúng file NGƯỜI DÙNG nêu, không phải file bộ não khai
        pub = goal_store().published(P, g.id, deliv) or {}
        f = BRAIN / deliv
        text = f.read_text(encoding="utf-8") if f.is_file() else ""
        # Chỉ báo hỗ trợ, KHÔNG phải căn cứ nghiệm thu (review e2e vòng 4): nội dung do người review chốt trên file
        # nguyên vẹn đã lưu ra ngoài thư mục tạm.
        candidate = G.content_contract(text, SCENARIO["items"])
        saved = G.preserve_artifact(f, Path(OUT).with_name(Path(OUT).stem + "-deliverable.md")) if OUT else \
            {"ok": False}
        rep["deliverable"] = {"path": deliv, "agent_path": R._deliverable_rel(cur), "sha256": _sha_file(f),
                              "published_sha256": pub.get("sha256"), "content_candidate": candidate,
                              "saved_copy": saved, "text_preview": _cut(text, 4000)}
        check("sản phẩm có ở đúng file người dùng nêu, bytes trên đĩa khớp hash host đã ghi khi đăng",
              f.is_file() and bool(pub) and _sha_file(f) == pub.get("sha256"))
        check("sản phẩm được lưu NGUYÊN VẸN ra ngoài thư mục tạm cho người review (hash khớp)",
              saved.get("ok") is True and saved.get("sha256") == _sha_file(f))
        rep["content_review"] = "pending"        # người review chốt; KHÔNG suy ra từ content_candidate
    else:
        check("dry: engine việc nền bị chặn trước khi gọi model, mục tiêu blocked có lý do",
              rs.get("run_state") == "blocked" and background_calls() == 0)
    rpt1 = reports(sid)
    check("tin báo của lượt nền về ĐÚNG phiên chat, mỗi tin có biên nhận của host",
          any(r["report"].startswith("outbox:") for r in rpt1) and all(r["receipt"] for r in rpt1 if r["report"]))

    # ───────────── Bước 3: giết và dựng lại lần nữa: không báo lặp, không gọi thêm ─────────────
    calls_before = background_calls()
    SRV.kill()
    rep["steps"]["start_C_s"] = round(SRV.start(), 1)
    time.sleep(75)   # hơn hai nhịp lập lịch (30 giây)
    keys = [r["report"] for r in reports(sid) if r["report"]]
    check("sau khởi động lại: không có tin báo lặp (khoá báo cáo duy nhất)", len(keys) == len(set(keys)))
    check("sau khởi động lại: không gọi thêm khi không có gì tới hạn", background_calls() == calls_before)

    # ───────────── Bước 4 và 5: người dùng trên thẻ, rồi điều kiện khép vòng theo kiểu mục tiêu ─────────────
    code, body = http("GET", f"/goals/{g.id}")
    v = body.get("goal") or {}
    check("API thẻ GET /goals/{id} trả trạng thái sống của mục tiêu", code == 200 and v.get("goal_id") == g.id)
    if MODE == "real":
        human = [c for c in v.get("criteria", []) if c.get("evaluator") == "human_confirmation"]
        if human:
            check("mục tiêu có tiêu chí người dùng duyệt thì phải có sản phẩm để duyệt (artifact_ref)",
                  bool(v.get("artifact_ref")))
            code, _b = http("POST", f"/goals/{g.id}/feedback",
                            json={"kind": "outcome_accepted", "expected_revision": v["revision"],
                                  "criterion_id": human[0]["id"], "artifact_ref": v.get("artifact_ref"),
                                  "idempotency_key": f"pilot-accept-{g.id}"})
            check("bấm Đạt yêu cầu qua API (kiểm Origin, đúng revision, đúng bản sản phẩm): 200", code == 200)
        cur = goal_store().get(P, g.id)
        # Khép vòng theo KIỂU KỊCH BẢN (hợp đồng ngoài), không theo cur.mode bộ não chọn.
        ok_m = wait_until(lambda: (goal_store().get(P, g.id).status == "active"
                                   and (goal_store().assessments(P, g.id) or [{}])[-1].get("verdict") == "met"
                                   and any(n["kind"] == "goal.maintained" and n["delivered"]
                                           for n in notices(g.id))), 120)
        check("maintain: đánh giá met, vẫn active, đã báo goal.maintained về phiên có biên nhận",
              bool(ok_m) and all(r["receipt"] for r in reports(sid) if r["report"]))
        met_at = max([float((a.get("payload") or a).get("evaluated_at") or 0) for a in goal_store().assessments(P, g.id)
                      if a.get("verdict") == "met"] or [0.0])
        wk = [w for w in goal_store().wakes(P, g.id) if w["kind"] == "work"]
        rep["review_wake"] = {"met_at": met_at, "due_at": wk[0]["due_at"] if wk else None}
        check("maintain: lịch xem lại nằm trong [6 giờ, 24 giờ] sau mốc đánh giá (cả hai đầu)",
              bool(wk) and met_at > 0 and G.review_wake_ok(wk[0]["due_at"], met_at, R.REVIEW_MIN_S, R.REVIEW_DEFAULT_S))
        code, _b = http("POST", f"/goals/{g.id}/commands", json={"command": "pause",
                                                                 "expected_revision": cur.revision})
        check("kết thúc pilot: người dùng tạm dừng qua API, không còn việc nền", code == 200
              and goal_store().get(P, g.id).paused)
        check("bước duyệt và khép vòng không gọi thêm model", background_calls() == calls_before)
        rep["final_notices"] = notices(g.id)
        rep["reports_in_session"] = len([r for r in reports(sid) if r["report"]])
    else:
        code, _b = http("POST", f"/goals/{g.id}/feedback",
                        json={"kind": "goal_fit_confirmed", "expected_revision": v.get("revision", 1)})
        check("dry: POST feedback qua kiểm Origin của server thật: 200", code == 200)
    check("ghi chú cũ (Notes/ghi-chu-cu.md) còn nguyên",
          KEEP.is_file() and hashlib.sha256(KEEP.read_bytes()).hexdigest() == _keep_sha)
except SystemExit as e:
    print(f"DỪNG: {e}")
    rep["stopped"] = str(e)
except Exception as e:  # noqa: BLE001
    check(f"bộ chạy không lỗi ({type(e).__name__}: {e})", False)
finally:
    SRV.kill()
    rep["host_engine_turns"] = {"brain": brain_turns, "background": background_calls(),
                                "total": brain_turns + background_calls()}
    check(f"tổng lượt engine cấp host trong trần {MAX_CALLS}", brain_turns + background_calls() <= MAX_CALLS)
    rep["servers"] = SRV.started
    rep["seconds_total"] = round(time.time() - t_start, 1)
    # Kết luận của lần chạy (review e2e vòng 4): kỹ thuật đạt thì nội dung CHỜ người review, không bao giờ tự "đạt".
    rep["acceptance"] = ("stopped" if rep.get("stopped") else "technical_failed" if _fails else
                         "pending_content_review" if MODE == "real" else "dry_ok")
    rep["checks"] = _log
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True,
                              timeout=10).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "server", "system"], cwd=str(ROOT),
                                    capture_output=True, text=True, timeout=10).stdout.strip())
    except Exception:  # noqa: BLE001
        head, dirty = "", None
    rep["commit"], rep["server_dirty"] = head, dirty
    print("E2E_REPORT " + json.dumps({k: rep[k] for k in ("mode", "host_engine_turns", "seconds_total") if k in rep},
                                     ensure_ascii=False))
    outp = OUT
    if outp:
        txt = json.dumps(rep, ensure_ascii=True, indent=2) + "\n"
        for secret_path in (str(BASE), str(Path.home())):
            txt = txt.replace(json.dumps(secret_path)[1:-1], "<path>")
        Path(outp).write_text(txt, encoding="utf-8", newline="\n")
    if not os.environ.get("JAVIS_RESONANCE_E2E_KEEP"):
        shutil.rmtree(BASE, ignore_errors=True)

if rep.get("acceptance") == "pending_content_review":
    print("\nOK (kỹ thuật): mọi kiểm kỹ thuật đạt. Nội dung CHỜ người review trên file đã lưu; CHƯA nghiệm thu pilot.")
    sys.exit(0)
if _fails or rep.get("stopped"):
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
