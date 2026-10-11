"""Resonance A4: pilot nộp sản phẩm qua hợp đồng host (thiết kế chốt D1), engine THẬT chỉ ở lượt chat của trợ lý.

    JAVIS_RESONANCE_A4_PILOT=dry  python tests/python/test_resonance_a4_pilot.py         # KHÔNG gọi model, mọi ca
    JAVIS_RESONANCE_A4_PILOT=real JAVIS_RESONANCE_PILOT_SETTINGS=<settings.json thật> \\
        JAVIS_RESONANCE_A4_OUT=<thư mục hồ sơ, chưa tồn tại> python tests/python/test_resonance_a4_pilot.py
                                                                                        # cần người dùng duyệt riêng

Không đặt biến thì bỏ qua (CI và tests/run.py không gọi gì).

Điều pilot cần chứng minh bằng model thật (phần còn lại đã có test và smoke engine giả):
1. Lượt chat của TRỢ LÝ với đích mới: bộ não tự lập mục tiêu và nộp bản qua công cụ chung `javis_submit_deliverable`;
   host GIỮ bản nháp, xin quyền trên thẻ, KHÔNG có file đích nào trước khi chủ cho phép.
2. Chủ dự án bấm Cho phép (API như nút thẻ, gửi đúng yêu cầu, bản nháp, sha): host đăng ĐÚNG bytes đã giữ, tiếp nhận,
   KHÔNG gọi thêm model.
3. Lượt chat thứ hai (phạm vi đã cấp): bộ não sửa mục tiêu và nộp bản 2; host tự đăng, không hỏi lại quyền.
4. Giết và dựng lại server: không gọi thêm, không báo lặp, kho nhất quán; cuối cùng tạm dừng mục tiêu.

Hạn mức, hai lớp, không thay nhau:
- Sổ LƯỢT CHAT thật (ChatLedger): tối đa 2 lượt, giữ chỗ và fsync TRƯỚC mỗi lần gửi, không đặt lại, không hoàn. Lượt
  lỗi, hết giờ, không có turn_done: sổ ĐÓNG, không gửi lượt nào nữa, không tự thử lại. Sổ đã có từ lần chạy trước thì
  từ chối chạy (không bao giờ đặt về 0).
- Trần KHO `JAVIS_RESONANCE_CALL_CEILING=0` cho mọi tiến trình server: KHÔNG lượt việc nền hay phép thử nào được gọi
  engine (kho chặn trước lời gọi, giữ qua khởi động lại).
Đơn vị là lượt engine cấp host: một lượt chat có thể gồm nhiều request nội bộ của SDK, không phải số request hay token.

dry chạy mỗi ca bằng một tiến trình con (ca chính và các ca âm: cổng chi phí, cổng xác thực, quyền (thẻ cũ 409), biên
nhận đăng không thành, lỗi engine, bộ não không nộp, bộ não tự ghi file đích, thiếu bằng chứng, sổ có lượt giữ chỗ
không kết quả). Lượt chat ở dry là MÔ PHỎNG trong tiến trình bằng đúng các hàm công cụ dùng; mọi bước khác (server
thật, API thẻ, giết và dựng lại) như real.
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

MODE = os.environ.get("JAVIS_RESONANCE_A4_PILOT", "").strip().lower()
SCEN = os.environ.get("JAVIS_RESONANCE_A4_SCENARIO", "").strip()
if MODE not in ("dry", "real"):
    print("pilot A4: bỏ qua (đặt JAVIS_RESONANCE_A4_PILOT=dry hoặc real để chạy)")
    print("\nOK")
    sys.exit(0)

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import _e2e_pilot_guard as G  # noqa: E402

CHAT_LIMIT = 2
STORE_CEILING = 0
TURN_WALL_S = 900
PORT = int(os.environ.get("JAVIS_RESONANCE_A4_PORT", "7792"))
SLUG = "tro-ly-tom-tat"

# ───────────── Đầu vào ĐÓNG BĂNG: không chọn dữ liệu lúc chạy ─────────────
FROZEN = {
    "agent_md": ("---\nname: Trợ lý tóm tắt\ndescription: Soạn bản tóm tắt cuộc họp\ngroup: Content\n---\n"
                 "Bạn soạn bản tóm tắt cuộc họp ngắn gọn, đúng nội dung chủ dự án đưa.\n"),
    "deliverable": "Inbox/tom-tat-hop.md",
    "turn_1": ("(Dữ liệu mô phỏng để thử nghiệm.) Em soạn giúp anh bản tóm tắt cuộc họp sáng nay, ghi vào "
               "Inbox/tom-tat-hop.md, phải có mục Kết luận. Nội dung họp: chốt ra mắt sản phẩm ngày 20/11; chị Lan "
               "lo kế hoạch truyền thông; anh Minh kiểm lại ngân sách quảng cáo; cả nhóm họp lại thứ Hai tuần sau."),
    "turn_2": ("(Dữ liệu mô phỏng để thử nghiệm.) Em thêm vào bản tóm tắt Inbox/tom-tat-hop.md một mục Việc tiếp "
               "theo, mỗi việc một dòng có người phụ trách: chị Lan gửi kế hoạch truyền thông trước thứ Sáu, anh Minh "
               "gửi bảng ngân sách trước thứ Năm."),
    # Hợp đồng nội dung ĐỘC LẬP với tiêu chí bộ não đề xuất (chỉ hỗ trợ người review, không tự nghiệm thu).
    "content_v1": ["Kết luận", "20/11", "Lan", "Minh"],
    "content_v2": ["Việc tiếp theo", "Lan", "thứ Sáu", "Minh", "thứ Năm"],
}
FROZEN_SHA = hashlib.sha256(json.dumps(FROZEN, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _sha(b) -> str:
    return hashlib.sha256(b if isinstance(b, bytes) else str(b).encode("utf-8")).hexdigest()


def _sha_file(p) -> str:
    return _sha(Path(p).read_bytes()) if p and Path(p).is_file() else ""


# ───────────── Sổ lượt chat thật ─────────────

class ChatLedger:
    """Sổ lượt chat, ghi xuống đĩa (fsync rồi os.replace) TRƯỚC mỗi lần gửi. `create()` chỉ dùng ở đầu một lần chạy mới
    và từ chối khi sổ đã có. Mọi lỗi đọc, sai cấu trúc, lượt giữ chỗ chưa có kết quả hay kết quả không phải `ok` đều
    ĐÓNG sổ: không gửi thêm."""

    OK = "ok"
    STATUSES = ("reserved", "ok", "engine_error", "timeout", "no_turn_done", "transport_error")

    def __init__(self, path: Path, limit: int):
        self.path, self.limit = Path(path), int(limit)

    @classmethod
    def create(cls, path: Path, limit: int, run_id: str) -> "ChatLedger":
        led = cls(path, limit)
        if led.path.exists():
            raise FileExistsError("sổ lượt chat đã có từ lần chạy trước; không đặt lại")
        led._write({"run_id": run_id, "limit": int(limit), "turns": []})
        return led

    def _write(self, st: dict) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(st, ensure_ascii=False, indent=1))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def _load(self) -> tuple:
        try:
            st = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            return None, f"ledger_unreadable: {type(e).__name__}"
        turns = st.get("turns") if isinstance(st, dict) else None
        if not isinstance(turns, list) or st.get("limit") != self.limit:
            return None, "ledger_bad_shape"
        for i, t in enumerate(turns, 1):
            if not isinstance(t, dict) or t.get("n") != i or t.get("status") not in self.STATUSES:
                return None, f"ledger_bad_turn_{i}"
        return st, ""

    def halted(self) -> str:
        st, err = self._load()
        if err:
            return err
        for t in st["turns"]:
            if t["status"] == "reserved":
                return "reserved_without_outcome"
            if t["status"] != self.OK:
                return f"turn_{t['n']}_{t['status']}"
        return ""

    def used(self) -> int:
        st, _ = self._load()
        return len(st["turns"]) if st else self.limit

    def reserve(self, label: str) -> tuple:
        h = self.halted()
        if h:
            return False, f"halted: {h}"
        st, _ = self._load()
        if len(st["turns"]) >= self.limit:
            return False, "limit"
        st["turns"].append({"n": len(st["turns"]) + 1, "label": label, "status": "reserved", "at": time.time()})
        self._write(st)
        return True, ""

    def settle(self, label: str, status: str) -> None:
        st, err = self._load()
        if err:
            return
        for t in st["turns"]:
            if t["label"] == label and t["status"] == "reserved":
                t["status"], t["settled_at"] = status, time.time()
        self._write(st)


# ───────────── Ca chạy (một tiến trình mỗi ca) ─────────────

def run_case(scen: str) -> int:
    """Một ca trọn: dựng, hai lượt chat (thật hay mô phỏng), Cho phép, giết và dựng lại, đối soát. Trả mã thoát."""
    base = Path(tempfile.mkdtemp(prefix="rsa4p-", dir=os.environ.get("TEMP") or None)).resolve()
    state, brains = base / "state", base / "brains"
    brain = brains / "Brain Default"
    for d in (state, brain / "Inbox", brain / "agents", brain / "Notes"):
        d.mkdir(parents=True, exist_ok=True)
    (brain / "agents" / f"{SLUG}.md").write_text(FROZEN["agent_md"], encoding="utf-8", newline="\n")
    keep = brain / "Notes" / "ghi-chu-cu.md"
    keep.write_text("Ghi chú cũ, không được đụng tới.\n", encoding="utf-8", newline="\n")
    keep_sha = _sha_file(keep)
    deliv = brain / FROZEN["deliverable"]
    if scen == "receipt":
        deliv.write_text("Bản anh tự viết trước đó.\n", encoding="utf-8", newline="\n")

    out_dir = Path(os.environ.get("JAVIS_RESONANCE_A4_OUT") or (base / "out"))
    if MODE == "real":
        if not os.environ.get("JAVIS_RESONANCE_A4_OUT"):
            print("FAIL pilot: chế độ real cần JAVIS_RESONANCE_A4_OUT (thư mục hồ sơ, chưa tồn tại)")
            return 1
        if out_dir.exists():
            print("FAIL pilot: JAVIS_RESONANCE_A4_OUT đã tồn tại; mỗi lần chạy thật một thư mục mới")
            return 1
        src = os.environ.get("JAVIS_RESONANCE_PILOT_SETTINGS", "")
        if not src or not Path(src).is_file():
            print("FAIL pilot: thiếu JAVIS_RESONANCE_PILOT_SETTINGS trỏ tới settings.json thật")
            return 1
        _m = (json.loads(Path(src).read_text(encoding="utf-8")).get("model") or {})
        model = {k: _m[k] for k in ("auxiliary", "main", "engine", "claude_model") if k in _m}
    else:
        model = {"auxiliary": {"provider": "grok-cli", "model": "grok-dry"}}
    out_dir.mkdir(parents=True, exist_ok=True)
    assert not any(k in model for k in ("claude_auth", "anthropic_api_key")), "settings pilot không có chế độ API key"
    (state / "settings.json").write_text(json.dumps({"model": model, "setup_done": True}, ensure_ascii=False),
                                         encoding="utf-8", newline="\n")

    os.environ["JAVIS_STATE_DIR"] = str(state)
    os.environ["BRAINS_DIR"] = str(brains)
    import resonance as R  # noqa: E402  - sau khi đặt JAVIS_STATE_DIR
    import resonance_store as RS  # noqa: E402
    import sessions as SSm  # noqa: E402
    import turn_context  # noqa: E402
    import luot_dang_chay  # noqa: E402

    key = str(brain.resolve())
    owner = RS.Principal("owner", "owner", key)
    host = RS.Principal("agent", "javis", key)
    origin = f"http://127.0.0.1:{PORT}"
    approved = (json.loads(os.environ["JAVIS_RESONANCE_A4_APPROVED"]) if os.environ.get("JAVIS_RESONANCE_A4_APPROVED")
                else {} if MODE == "real" else {"aux": {"provider": "grok-cli"}})
    pilot_vars = ("JAVIS_RESONANCE_TICK_PAUSED", "JAVIS_RESONANCE_CALL_CEILING", "JAVIS_CLAUDE_CLI", "JAVIS_CLAUDE_BIN",
                  "JAVIS_STATE_DIR", "BRAINS_DIR", "JAVIS_PORT")
    env0 = {k: v for k, v in G.clean_env(dict(os.environ)).items() if k not in pilot_vars}
    fails, log = [], []

    def check(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        log.append({"check": name, "ok": bool(cond)})
        if not cond:
            fails.append(name)
        return bool(cond)

    def store():
        return RS.GoalStore(state / "resonance.sqlite3")

    def sess():
        return SSm.SessionStore(state / "conversations.db")

    # Trợ lý bật qua kho như chủ dự án bật; phiên của trợ lý tạo sẵn (kênh agent:<slug>) để lượt chat là lượt trợ lý.
    agent = store().agent_set_enabled(owner, SLUG, True)
    sid = sess().create_session(brain=key, engine="pilot", model="pilot", channel=f"agent:{SLUG}")

    rep = {"mode": MODE, "scenario": scen, "frozen_sha256": FROZEN_SHA, "chat_limit": CHAT_LIMIT,
           "store_ceiling": STORE_CEILING, "unit": "lượt engine cấp host (không phải request nội bộ hay token)",
           "steps": {}, "turns": {}}
    run_id = f"a4-{int(time.time())}-{os.getpid()}"
    ledger_path = out_dir / "chat-ledger.json"
    if scen == "reserved":
        # Lần chạy trước chết giữa lượt: sổ còn dòng giữ chỗ không có kết quả.
        ChatLedger.create(ledger_path, CHAT_LIMIT, "trước").reserve("turn_1")
    try:
        led = ChatLedger.create(ledger_path, CHAT_LIMIT, run_id)
    except FileExistsError as e:
        led = ChatLedger(ledger_path, CHAT_LIMIT)
        rep["ledger_refused"] = str(e)
    limit_env = int(os.environ.get("JAVIS_RESONANCE_A4_MAX_CALLS", str(CHAT_LIMIT)))

    def resolve_cli() -> str:
        cp = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, 'server'); "
                             "from claude_cli import tim_binary; print(tim_binary('claude') or '')"],
                            cwd=str(ROOT), env=env0, capture_output=True, text=True, timeout=60)
        return (cp.stdout or "").strip().splitlines()[-1] if (cp.stdout or "").strip() else ""

    def resolve_engines() -> dict:
        code = ("import json, sys; sys.path.insert(0, 'server'); import aux_engine, config; "
                "m = (config.read_settings().get('model') or {}); "
                "print(json.dumps({'main': aux_engine.main_spec(), 'aux': aux_engine.read_spec(), "
                "'claude_model': m.get('claude_model')}))")
        cp = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env={**env0, "JAVIS_STATE_DIR": str(state)},
                            capture_output=True, text=True, timeout=120)
        try:
            return json.loads((cp.stdout or "").strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            return {}

    def auth_gate(cli: str) -> dict:
        """Không gọi model: engine sẽ chạy đúng cấu hình đã duyệt; `claude auth status` bằng đúng binary, cwd (brain),
        môi trường đã lọc là gói thuê bao Anthropic gốc; settings không có apiKeyHelper hay env chọn nhà cung cấp;
        không có settings do quản trị đặt. Chỉ ghi siêu dữ liệu, không ghi khoá hay token."""
        out = {"ok": False, "why": "", "engines": resolve_engines(), "approved": approved}
        if MODE == "dry":
            st = ({"loggedIn": True, "authMethod": "api_key", "apiProvider": "firstParty"} if scen == "auth"
                  else {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty",
                        "subscriptionType": "max"})
            ok, why = G.check_auth_status(st)
            out.update(ok=ok, why=why, auth={"dry_simulated": G.auth_metadata(st)})
            return out
        ok_e, why_e = G.check_engines(out["engines"], approved)
        if not approved or not ok_e:
            out["why"] = "chưa có cấu hình engine đã duyệt" if not approved else f"engine khác đã duyệt: {why_e}"
            return out
        if not cli:
            out["why"] = "không tìm thấy binary claude"
            return out
        try:
            st = json.loads(subprocess.run([cli, "auth", "status", "--json"], cwd=str(brain), env=env0,
                                           capture_output=True, text=True, timeout=60).stdout or "{}")
        except Exception as e:  # noqa: BLE001
            out["why"] = f"không chạy được auth status: {type(e).__name__}"
            return out
        out["auth"] = G.auth_metadata(st)
        ok, why = G.check_auth_status(st)
        if not ok:
            out["why"] = why
            return out
        cfg_dir = Path(st.get("configDirectory") or (Path.home() / ".claude"))
        paths = G.settings_paths(cfg_dir, brain)
        out["settings"] = G.scan_settings(paths)
        out["managed_sources"] = G.managed_sources(cfg_dir)
        out["not_assessed"] = G.ancillary_sources(paths)
        if out["settings"]["risky"]:
            out["why"] = "nguồn settings có apiKeyHelper hay env chọn nhà cung cấp/khoá"
        elif out["managed_sources"]:
            out["why"] = "có nguồn settings do quản trị đặt; môi trường này pilot chưa hỗ trợ"
        else:
            out["ok"] = True
        return out

    class Server:
        def __init__(self, cli: str):
            self.n, self.proc, self.cli, self.started = 0, None, cli, []

        def start(self, tick_paused: bool, wait_s: int = 150) -> float:
            self.n += 1
            env = {**env0, "JAVIS_PORT": str(PORT), "JAVIS_STATE_DIR": str(state), "BRAINS_DIR": str(brains),
                   "JAVIS_REQUIRE_LOGIN": "0", "PYTHONUTF8": "1", "JAVIS_RESONANCE_CALL_CEILING": str(STORE_CEILING)}
            if self.cli:
                env["JAVIS_CLAUDE_CLI"] = self.cli
            if tick_paused:
                env["JAVIS_RESONANCE_TICK_PAUSED"] = "1"
            self.started.append({"n": self.n, "tick_paused": tick_paused, "call_ceiling": STORE_CEILING})
            logf = open(base / f"server-{self.n}.log", "w", encoding="utf-8")
            self.proc = subprocess.Popen([sys.executable, "server/main.py"], cwd=str(ROOT), env=env, stdout=logf,
                                         stderr=subprocess.STDOUT,
                                         creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            import httpx
            t0 = time.time()
            while time.time() - t0 < wait_s:
                if self.proc.poll() is not None:
                    raise RuntimeError(f"server thoát sớm (server-{self.n}.log)")
                try:
                    if httpx.get(f"{origin}/health", timeout=2).status_code == 200:
                        return time.time() - t0
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(1)
            raise RuntimeError("server không lên kịp")

        def kill(self) -> None:
            if self.proc is None:
                return
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)
            else:
                self.proc.kill()
            self.proc.wait(timeout=30)
            self.proc = None
            time.sleep(2)

    def http(method, path, **kw):
        import httpx
        r = httpx.request(method, f"{origin}{path}", params={"brain": "brain"}, headers={"Origin": origin},
                          timeout=60, **kw)
        try:
            return r.status_code, r.json()
        except Exception:  # noqa: BLE001
            return r.status_code, {}

    def store_calls() -> int:
        import sqlite3
        c = sqlite3.connect(str(state / "resonance.sqlite3"))
        n = int(c.execute("SELECT COALESCE(SUM(calls_used),0) FROM goals").fetchone()[0])
        try:
            n += int(c.execute("SELECT COUNT(*) FROM call_ledger WHERE status='used'").fetchone()[0])
        except Exception:  # noqa: BLE001
            pass
        c.close()
        return n

    def goals_of_session() -> list:
        import sqlite3
        c = sqlite3.connect(str(state / "resonance.sqlite3"))
        ids = [r[0] for r in c.execute("SELECT id FROM goals WHERE brain_id=? AND session_id=?", (key, sid))]
        c.close()
        return [store().get(owner, i) for i in ids]

    def notices(goal_id) -> list:
        import sqlite3
        c = sqlite3.connect(str(state / "resonance.sqlite3"))
        rows = c.execute("SELECT id, kind, delivered_at FROM outbox WHERE goal_id=? ORDER BY id", (goal_id,)).fetchall()
        c.close()
        return [{"id": r[0], "kind": r[1], "delivered": r[2] is not None} for r in rows]

    def reports() -> list:
        """(khoá báo cáo, có biên nhận) của mọi thẻ tin báo trong phiên trợ lý."""
        ss, out = sess(), []
        for m in ss.get_messages(sid):
            if m["role"] != "assistant":
                continue
            for b in R.parse_goal_blocks(m.get("content") or ""):
                rk = b.get("report") or ""
                if rk:
                    out.append((rk, bool(ss.report_receipt(sid, rk, b["goal_id"]))))
        return out

    def cut(v, n=3000):
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        return s if len(s) <= n else s[:n] + f"...(+{len(s) - n})"

    async def ws_chat(message: str):
        import websockets
        frames, tools, answer = [], [], []
        async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws", origin=origin, max_size=None) as ws:
            await asyncio.wait_for(ws.recv(), 20)
            await ws.send(json.dumps({"message": message, "brain": "brain", "session_id": sid}))
            t0 = time.time()
            while time.time() - t0 < TURN_WALL_S:
                o = json.loads(await asyncio.wait_for(ws.recv(), TURN_WALL_S))
                t = o.get("type")
                frames.append(t)
                if t in ("tool_call", "tool", "tool_result"):
                    tools.append({k: cut(o.get(k)) for k in ("type", "tool", "name", "detail", "content", "input")
                                  if o.get(k) not in (None, "")})
                if t in ("response", "stream", "text") and o.get("content"):
                    answer.append(str(o.get("content")))
                if t == "turn_done":
                    break
        return frames, tools, "".join(answer)[-6000:]

    def sim_turn(n: int, message: str) -> dict:
        """Lượt chat MÔ PHỎNG (dry) bằng đúng các hàm công cụ dùng, trong ngữ cảnh lượt như run_turn dựng."""
        ss = sess()
        mid = ss.append_message(sid, "user", message)
        ref = R.message_ref(sid, mid)
        ag = store().agent(key, SLUG)
        p_agent = RS.Principal("agent", ag["agent_key"], key)
        st = store()
        deps = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "dry"}), budget=R.CallBudget(0),
                          clock=time.time, store=st, principal=host, brain_root=key)
        if scen == "engine" and n == 1:
            raise RuntimeError("engine_error (mô phỏng)")
        tok = turn_context.bind(turn_context.make(
            "dashboard", chat_id=sid, la_chu=True, session_id=sid, message_id=mid,
            agent={"key": ag["agent_key"], "slug": SLUG, "config_version": ag["config_version"]},
            authority_seq=st.authority_seq()))
        k = luot_dang_chay.bat_dau(f"web:{sid}", key, msg_id=mid, user_text=message)
        crit = [{"description": "Có mục Kết luận", "evaluator": "artifact_contract",
                 "params": {"path": FROZEN["deliverable"], "must_contain": ["Kết luận"]}}]
        body = ("# Tóm tắt cuộc họp\n\n- Ra mắt sản phẩm 20/11.\n- Chị Lan: kế hoạch truyền thông.\n"
                "- Anh Minh: ngân sách quảng cáo.\n\n## Kết luận\n\nHọp lại thứ Hai tuần sau.\n")
        if n == 2:
            body += "\n## Việc tiếp theo\n\n- Chị Lan gửi kế hoạch truyền thông trước thứ Sáu.\n" \
                    "- Anh Minh gửi bảng ngân sách trước thứ Năm.\n"
        try:
            if n == 1:
                g = asyncio.run(R.form_goal(ref, {
                    "principal": p_agent, "brain_root": key, "session_id": sid, "message_id": mid,
                    "user_text": message, "constraints": [], "budget_calls": 4,
                    "proposal": {"understanding": "Bản tóm tắt cuộc họp sáng nay", "relevant_quote": message[40:100],
                                 "criteria": crit, "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"},
                                 "stage": "delivery", "mode": "achieve"},
                    "hold_until": time.time() + R.HANDOFF_HOLD_S, "authority_seq": st.authority_seq(),
                    "agent_key": ag["agent_key"], "agent_version": ag["config_version"]},
                    R.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=R.CallBudget(0), store=st)))
            else:
                g0 = goals_of_session()[0]
                g = R.revise_goal(st, p_agent, g0.id, g0.revision,
                                  {"understanding": "Bản tóm tắt cuộc họp sáng nay, thêm Việc tiếp theo",
                                   "relevant_quote": message[40:100], "criteria": crit},
                                  {"message_ref": ref, "session_id": sid, "message_id": mid, "user_text": message,
                                   "constraints": [], "user_unsure": False, "reason": "góp ý",
                                   "hold_until": time.time() + R.HANDOFF_HOLD_S, "authority_seq": st.authority_seq(),
                                   "agent_key": ag["agent_key"], "agent_version": ag["config_version"]})[0]
            if scen == "native" and n == 1:
                deliv.write_text(body, encoding="utf-8", newline="\n")
            if not (scen == "nosubmit" and n == 1):
                R.submit_deliverable(turn_context.current(), {"path": FROZEN["deliverable"], "content": body}, deps)
        finally:
            luot_dang_chay.ket_thuc(k)
            turn_context.reset(tok)
        R.handoff_after_turn(g.id, ref, deps)
        ss.append_message(sid, "assistant", "Em đã nhận việc.\n" + R.goal_block(g.id, g.revision))
        return {"frames": {"simulated": 1}, "tools": [], "answer": "(mô phỏng)"}

    def chat(n: int, message: str) -> tuple:
        """Một lượt chat qua sổ: giữ chỗ TRƯỚC khi gửi, chốt kết quả sau. Không thử lại."""
        label = f"turn_{n}"
        if led.used() + 1 > limit_env:
            return False, "cost_gate: vượt hạn mức lượt chat đã duyệt"
        ok, why = led.reserve(label)
        if not ok:
            return False, why
        before = G.snapshot_files(brain)
        t0 = time.time()
        try:
            if MODE == "real":
                frames, tools, answer = asyncio.run(ws_chat(message))
                status = "ok" if frames and frames[-1] == "turn_done" else "no_turn_done"
                res = {"frames": {k: frames.count(k) for k in sorted(set(f for f in frames if f))}, "tools": tools,
                       "answer": answer}
            else:
                res = sim_turn(n, message)
                status = "ok"
        except asyncio.TimeoutError:
            status, res = "timeout", {}
        except RuntimeError as e:
            status, res = ("engine_error" if "engine_error" in str(e) else "transport_error"), {"error": str(e)}
        except Exception as e:  # noqa: BLE001
            status, res = "transport_error", {"error": f"{type(e).__name__}: {e}"}
        led.settle(label, status)
        res.update(status=status, seconds=round(time.time() - t0, 1),
                   brain_files=G.snapshot_diff(before, G.snapshot_files(brain)))
        rep["turns"][label] = res
        return status == "ok", status

    cli = resolve_cli() if MODE == "real" else ""
    srv = Server(cli)
    t_start = time.time()
    g = None
    try:
        # ───────────── Bước 0: cổng chi phí và xác thực, TRƯỚC mọi lượt chat (không gọi model) ─────────────
        if rep.get("ledger_refused"):
            raise SystemExit("dừng: " + rep["ledger_refused"])
        if not check(f"cổng chi phí: lượt chat dự kiến ({CHAT_LIMIT}) trong hạn mức đã duyệt ({limit_env})",
                     CHAT_LIMIT <= limit_env):
            raise SystemExit("dừng trước khi gửi tin: hạn mức đã duyệt nhỏ hơn số lượt kịch bản cần")
        rep["steps"]["start_A_s"] = round(srv.start(tick_paused=True), 1)
        gate = auth_gate(cli)
        rep["auth_gate"] = gate
        if not check(f"cổng xác thực: gói thuê bao Anthropic gốc, đúng engine đã duyệt ({gate.get('why') or 'đạt'})",
                     gate["ok"]):
            raise SystemExit("dừng trước khi gửi tin: không chứng minh được chỉ dùng gói thuê bao")

        # ───────────── Bước 1: lượt chat 1, đích mới: giữ bản nháp, xin quyền, không có file ─────────────
        ok, why = chat(1, FROZEN["turn_1"])
        if not check(f"lượt chat 1 kết thúc bình thường ({why})", ok):
            raise SystemExit(f"dừng: lượt chat 1 {why}; không thử lại")
        gs = goals_of_session()
        if not check("bộ não lập ĐÚNG MỘT mục tiêu gắn phiên trợ lý", len(gs) == 1):
            raise SystemExit("dừng: không có mục tiêu để theo dõi (ghi nhận, không thử lại)")
        g = gs[0]
        check("mục tiêu thuộc trợ lý của phiên (host gắn, không từ lời model)", g.agent_key == agent["agent_key"])
        check(f"đích của mục tiêu đúng file người dùng nêu ({FROZEN['deliverable']})",
              R._deliverable_rel(g) == FROZEN["deliverable"])
        sc = store().scope_state(owner, g.id)
        drafts = store().submissions(owner, g.id, limit=5, statuses=("awaiting_scope",), revision=g.revision)
        rep["after_turn_1"] = {"scope": sc.get("state"), "drafts": [{k: d[k] for k in ("source", "status", "sha256",
                                                                                         "size")} for d in drafts]}
        check("D1: phạm vi CHỜ chủ cho phép, lời chat không cấp quyền", sc.get("state") == "pending")
        if not check("bộ não nộp bản qua công cụ chung: host giữ bản nháp chờ quyền (submit_tool)",
                     bool(drafts) and drafts[0]["source"] == "submit_tool"):
            raise SystemExit("dừng: không có bản nháp để chủ cho phép (ghi nhận như kết quả pilot)")
        if not check("không có file đích trước khi chủ cho phép (không ghi native)", not deliv.is_file()
                     if scen != "receipt" else deliv.read_text(encoding="utf-8") == "Bản anh tự viết trước đó.\n"):
            raise SystemExit("dừng: file đích xuất hiện trước khi chủ cho phép")
        check("lượt chat không mở lượt việc nền hay gọi engine cấp kho", store_calls() == 0)

        # ───────────── Bước 2: giết A, dựng B; chủ bấm Cho phép qua API ─────────────
        # B vẫn tạm dừng nhịp: mục tiêu không được kết thúc giữa hai lượt chat (lượt 2 cần mục tiêu còn mở để sửa). Nhịp
        # chạy lại ở C, cùng trần kho 0.
        srv.kill()
        rep["steps"]["start_B_s"] = round(srv.start(tick_paused=True), 1)
        code, body = http("GET", f"/goals/{g.id}")
        v = body.get("goal") or {}
        scv = v.get("scope") or {}
        dr = scv.get("draft") or {}
        check("thẻ sau khởi động lại vẫn xin quyền đúng đường, kèm bản nháp (mã, sha)",
              code == 200 and scv.get("state") == "pending" and scv.get("path") == FROZEN["deliverable"]
              and dr.get("sha256") == drafts[0]["sha256"])
        req = {"command": "approve_scope", "expected_revision": v.get("revision"),
               "request_id": str((scv.get("request") or {}).get("id") or ""), "path": scv.get("path"),
               "submission_id": dr.get("submission_id"), "sha256": dr.get("sha256")}
        if scen == "permission":
            # Thẻ cũ: "tab khác" đã bấm Không trước; Cho phép trên thẻ cũ phải 409 và không ghi gì.
            http("POST", f"/goals/{g.id}/commands", json={"command": "deny_scope",
                                                          "expected_revision": v.get("revision"),
                                                          "request_id": req["request_id"]})
        calls0 = store_calls()
        code, ab = http("POST", f"/goals/{g.id}/commands", json=req)
        rep["approve"] = {"code": code, "status": ab.get("status"), "publish": ab.get("publish")}
        if not check("Cho phép: 200, đăng ĐÚNG bản nháp đã giữ (publish succeeded)",
                     code == 200 and ab.get("publish") == "succeeded"):
            raise SystemExit(f"dừng: Cho phép trả {code}/{ab.get('publish') or ab.get('error')}")
        s1 = store().submission(owner, ab.get("submission_id") or "") or {}
        check("bytes file đích khớp sha bản nháp chủ đã duyệt, bản nộp đã đăng và đã tiếp nhận",
              _sha_file(deliv) == dr.get("sha256") and s1.get("status") == "published" and bool(s1.get("adopted_at")))
        check("Cho phép không gọi thêm model", store_calls() == calls0)
        saved1 = G.preserve_artifact(deliv, out_dir / "a4-deliverable-v1.md") if scen != "evidence" else {"ok": False}
        rep["deliverable_v1"] = {"sha256": _sha_file(deliv), "saved": saved1,
                                 "content_candidate": [k for k in FROZEN["content_v1"]
                                                       if k.lower() not in deliv.read_text(encoding="utf-8").lower()]}
        if not check("bản 1 lưu NGUYÊN VẸN ra hồ sơ cho người review (hash khớp)",
                     saved1.get("ok") is True and saved1.get("sha256") == _sha_file(deliv)):
            raise SystemExit("dừng: thiếu bằng chứng sản phẩm bản 1")

        # ───────────── Bước 3: lượt chat 2, phạm vi đã cấp: tự đăng bản 2, không hỏi lại ─────────────
        ok, why = chat(2, FROZEN["turn_2"])
        if not check(f"lượt chat 2 kết thúc bình thường ({why})", ok):
            raise SystemExit(f"dừng: lượt chat 2 {why}; không thử lại")
        g2 = store().get(owner, g.id)
        subs = store().submissions(owner, g.id, limit=20)
        latest = next((s for s in subs if s["revision"] == g2.revision and s["source"] == "submit_tool"), None)
        sc2 = store().scope_state(owner, g.id)
        rep["after_turn_2"] = {"revision": g2.revision, "scope": sc2.get("state"),
                               "subs": [(s["source"], s["status"], s["revision"]) for s in subs]}
        check("lượt 2 sửa mục tiêu (revision mới) và nộp bản 2 qua công cụ chung", g2.revision > g.revision
              and latest is not None)
        check("phạm vi đã cấp: không có yêu cầu quyền mới", sc2.get("state") == "granted" and not sc2.get("request"))
        check("bản 2 được host tự đăng, bytes khớp sha bản nộp, đã tiếp nhận",
              latest is not None and latest["status"] == "published" and _sha_file(deliv) == latest["sha256"]
              and bool(latest.get("adopted_at")))
        saved2 = G.preserve_artifact(deliv, out_dir / "a4-deliverable-v2.md")
        rep["deliverable_v2"] = {"sha256": _sha_file(deliv), "saved": saved2,
                                 "content_candidate": [k for k in FROZEN["content_v2"]
                                                       if k.lower() not in deliv.read_text(encoding="utf-8").lower()]}
        check("bản 2 lưu NGUYÊN VẸN ra hồ sơ cho người review", saved2.get("ok") is True)

        # ───────────── Bước 4: giết B, dựng C: không gọi thêm, không báo lặp; tạm dừng ─────────────
        calls1 = store_calls()
        srv.kill()
        rep["steps"]["start_C_s"] = round(srv.start(tick_paused=False), 1)
        time.sleep(75 if MODE == "real" else 35)
        check("sau khởi động lại: trần kho 0 giữ, không lượt engine cấp kho nào", store_calls() == calls1 == 0)
        ns = notices(g.id)
        keys = reports()
        check("sau khởi động lại: mỗi tin báo một khoá báo cáo, có biên nhận của host, không lặp",
              len(keys) == len(set(k for k, _r in keys)) and all(r for _k, r in keys))
        g3 = store().get(owner, g.id)
        if g3.status == "active":
            code, _b = http("POST", f"/goals/{g.id}/commands", json={"command": "pause",
                                                                      "expected_revision": g3.revision})
            check("kết thúc: tạm dừng qua API, không còn việc nền", code == 200 and store().get(owner, g.id).paused)
        rep["final"] = {"status": store().get(owner, g.id).status, "notices": ns}
        check("ghi chú cũ còn nguyên", _sha_file(keep) == keep_sha)
    except SystemExit as e:
        print(f"DỪNG: {e}")
        rep["stopped"] = str(e)
    except Exception as e:  # noqa: BLE001
        check(f"bộ chạy không lỗi ({type(e).__name__}: {e})", False)
    finally:
        srv.kill()
        rep["ledger"] = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else None
        rep["model_turns"] = {"chat_real": led.used() if MODE == "real" else 0,
                              "chat_simulated": led.used() if MODE == "dry" else 0,
                              "store": store_calls() if (state / "resonance.sqlite3").exists() else 0}
        check(f"tổng lượt chat thật trong hạn mức {CHAT_LIMIT}", rep["model_turns"]["chat_real"] <= CHAT_LIMIT)
        rep["servers"] = srv.started
        rep["seconds_total"] = round(time.time() - t_start, 1)
        rep["acceptance"] = ("stopped" if rep.get("stopped") else "technical_failed" if fails else
                             "pending_content_review" if MODE == "real" else "dry_ok")
        rep["checks"] = log
        try:
            rep["commit"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True,
                                           text=True, timeout=10).stdout.strip()
            rep["server_dirty"] = bool(subprocess.run(["git", "status", "--porcelain", "--", "server", "system",
                                                       "dashboard"], cwd=str(ROOT), capture_output=True, text=True,
                                                      timeout=10).stdout.strip())
        except Exception:  # noqa: BLE001
            rep["commit"], rep["server_dirty"] = "", None
        txt = json.dumps(rep, ensure_ascii=True, indent=2) + "\n"
        for secret in (str(base), str(Path.home())):
            txt = txt.replace(json.dumps(secret)[1:-1], "<path>")
        (out_dir / f"a4-pilot-{MODE}-{scen or 'main'}.json").write_text(txt, encoding="utf-8", newline="\n")
        print("A4_PILOT " + json.dumps({k: rep.get(k) for k in ("mode", "scenario", "acceptance", "model_turns")},
                                       ensure_ascii=False))
        if not os.environ.get("JAVIS_RESONANCE_A4_KEEP"):
            shutil.rmtree(base, ignore_errors=True)
    return 0 if rep["acceptance"] in ("dry_ok", "pending_content_review") else 1


# ───────────── dry: mọi ca, mỗi ca một tiến trình con; real: đúng một ca chính ─────────────

DRY_CASES = {
    # ca: (biến môi trường thêm, kết luận mong đợi, câu kiểm phải có trong output)
    "main": ({}, "dry_ok", "bản 2 được host tự đăng"),
    "cost": ({"JAVIS_RESONANCE_A4_MAX_CALLS": "1"}, "stopped", "dừng trước khi gửi tin: hạn mức"),
    "auth": ({}, "stopped", "dừng trước khi gửi tin: không chứng minh"),
    "permission": ({}, "stopped", "Cho phép trả 409"),
    "receipt": ({}, "stopped", "Cho phép trả 200/conflict"),
    "engine": ({}, "stopped", "lượt chat 1 engine_error; không thử lại"),
    "nosubmit": ({}, "stopped", "không có bản nháp để chủ cho phép"),
    "native": ({}, "stopped", "file đích xuất hiện trước khi chủ cho phép"),
    "evidence": ({}, "stopped", "thiếu bằng chứng sản phẩm bản 1"),
    "reserved": ({}, "stopped", "sổ lượt chat đã có từ lần chạy trước"),
}

if SCEN:
    sys.exit(run_case(SCEN))
if MODE == "real":
    sys.exit(run_case("main"))

bad = []
for name, (extra, want, needle) in DRY_CASES.items():
    env = {**os.environ, "JAVIS_RESONANCE_A4_SCENARIO": name, "PYTHONIOENCODING": "utf-8", **extra}
    env.pop("JAVIS_RESONANCE_A4_OUT", None)
    cp = subprocess.run([sys.executable, str(HERE)], cwd=str(ROOT), env=env, capture_output=True, text=True,
                        encoding="utf-8", timeout=900)
    if os.environ.get("JAVIS_RESONANCE_A4_DRY_DIR"):
        # Bằng chứng từng ca: output đầy đủ của tiến trình con (không có khoá hay đường dẫn cá nhân).
        dd = Path(os.environ["JAVIS_RESONANCE_A4_DRY_DIR"])
        dd.mkdir(parents=True, exist_ok=True)
        (dd / f"a4-pilot-dry-{name}.txt").write_text(cp.stdout + cp.stderr[-4000:], encoding="utf-8", newline="\n")
    line = next((x for x in cp.stdout.splitlines() if x.startswith("A4_PILOT ")), "")
    got = json.loads(line[len("A4_PILOT "):]) if line else {}
    ok = got.get("acceptance") == want and needle in cp.stdout and \
        (got.get("model_turns") or {}).get("chat_real", 1) == 0
    print(("ok   " if ok else "FAIL ") + f"ca {name}: kết luận {got.get('acceptance')} (mong {want}), "
          f"lượt thật {(got.get('model_turns') or {}).get('chat_real')}")
    if not ok:
        bad.append(name)
        print("\n".join("    " + x for x in cp.stdout.splitlines()[-25:]))
if bad:
    print(f"\n{len(bad)} FAIL:", bad)
    sys.exit(1)
print("\nOK")
