"""Resonance A5: pilot đội một agent làm, một agent review trên đường host thật.

    JAVIS_RESONANCE_A5_PILOT=dry  python tests/python/test_resonance_a5_pilot.py         # KHÔNG gọi model, mọi ca
    JAVIS_RESONANCE_A5_PILOT=real JAVIS_RESONANCE_PILOT_SETTINGS=<settings.json thật> \\
        JAVIS_RESONANCE_A5_OUT=<thư mục hồ sơ, chưa tồn tại> JAVIS_RESONANCE_A5_APPROVED='<json engine đã duyệt>' \\
        JAVIS_RESONANCE_A5_MAX_CALLS=<số lượt đã duyệt> JAVIS_RESONANCE_A5_INPUTS_SHA=<hash đầu vào đã duyệt> \\
        python tests/python/test_resonance_a5_pilot.py                                  # cần chủ dự án duyệt riêng

Không đặt biến thì bỏ qua (CI và tests/run.py không gọi gì).

Điều pilot cần chứng minh bằng model thật (phần còn lại đã có test và smoke engine giả):
1. Việc nền của VAI LÀM (agent làm, engine việc nền) viết bản đạt kiểm khách quan; host đăng đúng bytes vào file đích
   theo quyền A4 chủ đã cấp.
2. Việc nền của VAI REVIEW (agent review khác danh tính, lời dặn review, cùng engine việc nền theo thiết kế) đọc ẢNH
   CHỤP của đúng bản đã tiếp nhận (hash, revision, mã reviewer ghim) và ra kết luận đọc được.
3. Nhánh xảy ra thật được ghi đúng: đạt ngay; hay cần sửa thì vai làm sửa theo góp ý rồi review lại. Không ép nhánh.
4. Giết và dựng lại server: không lượt nào được gọi thêm, sổ và kho nhất quán.

Lập mục tiêu KHÔNG dùng lượt chat: bộ chạy gọi `form_goal` (đúng hàm tool `javis_goal` và `/goal-requests` dùng) với
lời giao và đề xuất ĐÓNG BĂNG, trong phiên của agent làm; không lượt model nào. Đây là gieo trạng thái bằng hàm host
thật, không phải engine giả; nó KHÔNG chứng minh bộ não chat tự định tuyến tới `javis_goal` (đã có ở pilot A4). Chủ cho
phép phạm vi qua đúng API của nút trên thẻ.

Hạn mức, nhiều lớp, không thay nhau:
- Sổ lượt theo vai của pilot (`_a5_pilot_server.py`): giữ chỗ và fsync TRƯỚC khi dựng engine cho mỗi lượt; trần
  vai (maker, reviewer) và trần tổng; lượt lỗi, huỷ, thiếu kết quả vẫn tính và ĐÓNG sổ; hết trần hay sổ đóng thì không
  dựng engine (host hoàn lượt theo đường not-run của A5) và sổ ghi một lần thử bị chặn. Sổ đã có từ trước thì từ chối.
- Trần kho `JAVIS_RESONANCE_CALL_CEILING`: bằng trần tổng của pilot khi chạy việc nền; 0 khi dựng và khi dựng lại.
- Trần sản phẩm của đội (8 lượt, 4/4, hai vòng sửa) giữ nguyên; trần pilot nhỏ hơn và là thứ được duyệt.
Đơn vị là lượt engine cấp host (một lần dựng engine cho một lượt làm hay review), không phải request nội bộ hay token.

dry chạy mỗi ca bằng một tiến trình con. Ở dry, settings dùng provider không tồn tại và launcher thay hàm dựng engine
việc nền bằng engine giả đọc kịch bản; hàm dựng "thật" là bẫy (chạm tới là ghi sự kiện và dừng). Không có lượt chat
nào ở cả hai chế độ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MODE = os.environ.get("JAVIS_RESONANCE_A5_PILOT", "").strip().lower()
SCEN = os.environ.get("JAVIS_RESONANCE_A5_SCENARIO", "").strip()
if MODE not in ("dry", "real"):
    print("pilot A5: bỏ qua (đặt JAVIS_RESONANCE_A5_PILOT=dry hoặc real để chạy)")
    print("\nOK")
    sys.exit(0)

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import _e2e_pilot_guard as G  # noqa: E402

# ───────────── Hạn mức của pilot (đề xuất; real dùng đúng số đã duyệt) ─────────────
CAPS = {"maker": 2, "reviewer": 2, "total": 4}
MIN_CALLS = 2                    # nhánh ngắn nhất (làm 1, review 1 đạt) cần 2 lượt
TOKEN_MIN_S = 1800
PHASE_B_WALL_S = 1800 if MODE == "real" else 420
QUIET_S = 300                    # không còn lịch làm việc trong khoảng này và không có lượt đang chạy: dừng quan sát
POLL_S = 5
RESTART_WAIT_S = 95 if MODE == "real" else 70
PORT = int(os.environ.get("JAVIS_RESONANCE_A5_PORT", "7793"))
MAKER, REVIEWER = "nguoi-lam-tom-tat", "nguoi-duyet-tom-tat"
DELIV = "Inbox/tom-tat-hop-a5.md"

# ───────────── Đầu vào ĐÓNG BĂNG ─────────────
FROZEN = {
    "maker_md": ("---\nname: Người làm tóm tắt\ndescription: Soạn bản tóm tắt cuộc họp\ntags:\n- Content\n---\n"
                 "Bạn soạn bản tóm tắt cuộc họp ngắn gọn, đúng nội dung chủ dự án đưa, có mục Kết luận và mục Việc tiếp "
                 "theo.\n"),
    "reviewer_md": ("---\nname: Người duyệt tóm tắt\ndescription: Đọc kỹ bản tóm tắt trước khi giao\ntags:\n- Review\n"
                    "---\nBạn đọc kỹ bản tóm tắt: đúng nội dung cuộc họp, có mục Kết luận, mỗi việc tiếp theo có người "
                    "phụ trách và hạn. Thiếu thì yêu cầu sửa và nói rõ cần sửa gì.\n"),
    "deliverable": DELIV,
    "user_text": ("(Dữ liệu mô phỏng để thử nghiệm.) Em lo giúp anh bản tóm tắt cuộc họp sáng nay cho tới khi đạt: ghi "
                  "vào Inbox/tom-tat-hop-a5.md, có mục Kết luận và mục Việc tiếp theo (mỗi việc một dòng, có người phụ "
                  "trách và hạn). Nội dung họp: chốt ra mắt sản phẩm ngày 20/11; chị Lan gửi kế hoạch truyền thông "
                  "trước thứ Sáu; anh Minh gửi bảng ngân sách quảng cáo trước thứ Năm; cả nhóm họp lại thứ Hai tuần "
                  "sau."),
    "proposal": {
        "understanding": "Bản tóm tắt cuộc họp sáng nay ở Inbox/tom-tat-hop-a5.md, có Kết luận và Việc tiếp theo",
        "relevant_quote": "Em lo giúp anh bản tóm tắt cuộc họp sáng nay cho tới khi đạt",
        "criteria": [
            {"description": "Có mục Kết luận", "evaluator": "artifact_contract",
             "params": {"path": DELIV, "must_contain": ["Kết luận"]}},
            {"description": "Có mục Việc tiếp theo, mỗi việc có người phụ trách và hạn", "evaluator": "artifact_contract",
             "params": {"path": DELIV, "must_contain": ["Việc tiếp theo"]}}],
        "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"},
        "stage": "delivery", "mode": "achieve"},
    # Hợp đồng nội dung ĐỘC LẬP, chỉ hỗ trợ người đọc hồ sơ; không tự nghiệm thu nội dung.
    "content_hint": ["Kết luận", "Việc tiếp theo", "20/11", "Lan", "thứ Sáu", "Minh", "thứ Năm"],
    "caps": CAPS,
}
FROZEN_SHA = hashlib.sha256(json.dumps(FROZEN, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

# Kịch bản engine giả (chỉ dry).
_V1 = ("# Tóm tắt cuộc họp\n\n- Chốt ra mắt sản phẩm 20/11.\n\n## Kết luận\n\nRa mắt 20/11; họp lại thứ Hai tuần sau.\n\n"
       "## Việc tiếp theo\n\n- Chị Lan: gửi kế hoạch truyền thông, trước thứ Sáu.\n"
       "- Anh Minh: gửi bảng ngân sách quảng cáo, trước thứ Năm.\n")
_V2 = _V1 + "\n_Bản sửa theo góp ý: ghi rõ hạn của từng việc._\n"
_V3 = _V1 + "\n_Bản sửa lần hai._\n"


def _verdict(v, oks, fixes=""):
    return json.dumps({"verdict": v, "criteria": [{"index": i, "ok": ok, "reason": "x"} for i, ok in enumerate(oks)],
                       "fixes": fixes}, ensure_ascii=False)


_PASS = _verdict("pass", (True, True))
_CHANGES = _verdict("needs_changes", (True, False), "Ghi rõ hạn của từng việc")
DRY_SCRIPTS = {
    "main_pass": {"work": [_V1], "review": [_PASS]},
    "main_fix": {"work": [_V1, _V2], "review": [_CHANGES, _PASS]},
    "fix_cap": {"work": [_V1, _V2, _V3], "review": [_CHANGES, _CHANGES, _PASS]},
    "ledger_cap": {"work": [_V1, _V2, _V3], "review": [_CHANGES, _CHANGES, _PASS]},
    "review_unknown": {"work": [_V1], "review": ["Bản này ổn, không có JSON."]},
    "maker_error": {"work": [{"error": "lỗi engine giả của vai làm"}], "review": [_PASS]},
    "reviewer_error": {"work": [_V1], "review": [{"error": "lỗi engine giả của vai review"}]},
    # Bản làm thiếu mục "Việc tiếp theo": không đạt kiểm khách quan, không có review; host hẹn thử lại sau 15 phút.
    "maker_not_met": {"work": ["# Tóm tắt cuộc họp\n\n## Kết luận\n\nRa mắt 20/11.\n"], "review": [_PASS]},
    # Engine của vai làm treo lâu hơn trần thời gian của giai đoạn việc nền (dry đặt trần 60 giây cho ca này).
    "timeout": {"work": [{"sleep": 900}], "review": [_PASS]},
    "report_fault": {"work": [_V1], "review": [_PASS]},
    "recovery_fault": {"work": [_V1], "review": ["Bản này ổn, không có JSON."]},
    "report_fault_technical": {"work": [{"error": "lỗi engine giả của vai làm"}], "review": [_PASS]},
    # Khung final báo lỗi: host kết luận engine_result_error; sổ phải đóng.
    "final_is_error": {"work": [{"events": [{"type": "final", "is_error": True, "subtype": "error_during_execution",
                                             "content": "Engine báo lỗi."}]}], "review": [_PASS]},
}


def _sha(b) -> str:
    return hashlib.sha256(b if isinstance(b, bytes) else str(b).encode("utf-8")).hexdigest()


def _sha_file(p) -> str:
    return _sha(Path(p).read_bytes()) if p and Path(p).is_file() else ""


def read_ledger(path: Path) -> tuple:
    """(sổ, "") hay (None, lý do). Sổ thiếu, đọc lỗi, sai cấu trúc hay trần khác trần đã duyệt là CHƯA XÁC MINH, không
    bao giờ là 0 lượt. Cùng hàm đọc với launcher (`_a5_pilot_ledger.RoleLedger.load`)."""
    import _a5_pilot_ledger as PL
    st, err = PL.RoleLedger(path, {}).load()
    if err:
        return None, f"unverified: {err}"
    if st.get("caps") != CAPS:
        return None, "unverified: trần trong sổ khác trần đã duyệt"
    return st, ""


import _a5_pilot_ledger as PL  # noqa: E402  - hàm dùng chung, test ở test_resonance_a5_pilot_gate.py
from _a5_pilot_ledger import classify, ledger_counts  # noqa: E402


# ───────────── Ca chạy (một tiến trình mỗi ca) ─────────────

def run_case(scen: str) -> int:
    base = Path(tempfile.mkdtemp(prefix="rsa5p-", dir=os.environ.get("TEMP") or None)).resolve()
    state, brains = base / "state", base / "brains"
    brain = brains / "Brain Default"
    for d in (state, brain / "Inbox", brain / "agents", brain / "Notes", brain / "Javis"):
        d.mkdir(parents=True, exist_ok=True)
    (brain / "agents" / f"{MAKER}.md").write_text(FROZEN["maker_md"], encoding="utf-8", newline="\n")
    (brain / "agents" / f"{REVIEWER}.md").write_text(FROZEN["reviewer_md"], encoding="utf-8", newline="\n")
    keep = brain / "Notes" / "ghi-chu-cu.md"
    keep.write_text("Ghi chú cũ, không được đụng tới.\n", encoding="utf-8", newline="\n")
    keep_sha = _sha_file(keep)
    deliv = brain / DELIV

    # Hồ sơ nằm NGOÀI sandbox để sandbox dọn được mà không mất bằng chứng: real dùng thư mục chủ dự án chỉ định; dry do bộ
    # điều phối cấp mỗi ca một thư mục mới; không có thì nằm trong sandbox (và sandbox không bao giờ bị dọn).
    if MODE == "dry" and os.environ.get("JAVIS_RESONANCE_A5_DRY_DIR"):
        out_dir = Path(os.environ["JAVIS_RESONANCE_A5_DRY_DIR"]) / scen
    else:
        out_dir = Path(os.environ.get("JAVIS_RESONANCE_A5_OUT") or (base / "out"))
    approved_max = int(os.environ.get("JAVIS_RESONANCE_A5_MAX_CALLS", str(CAPS["total"])))
    if MODE == "real":
        need = ("JAVIS_RESONANCE_A5_OUT", "JAVIS_RESONANCE_PILOT_SETTINGS", "JAVIS_RESONANCE_A5_APPROVED",
                "JAVIS_RESONANCE_A5_MAX_CALLS", "JAVIS_RESONANCE_A5_INPUTS_SHA", "JAVIS_RESONANCE_A5_APPROVED_SHA")
        miss = [k for k in need if not os.environ.get(k)]
        if miss:
            print("FAIL pilot: real thiếu " + ", ".join(miss))
            return 1
        if os.environ["JAVIS_RESONANCE_A5_INPUTS_SHA"] != FROZEN_SHA:
            print("FAIL pilot: hash đầu vào khác bộ đã duyệt")
            return 1
        if out_dir.exists():
            print("FAIL pilot: JAVIS_RESONANCE_A5_OUT đã tồn tại; mỗi lần chạy thật một thư mục mới")
            return 1
        if out_dir.resolve().is_relative_to(Path(ROOT).resolve()):
            print("FAIL pilot: JAVIS_RESONANCE_A5_OUT phải nằm ngoài checkout (checkout phải sạch)")
            return 1
        _m = json.loads(Path(os.environ["JAVIS_RESONANCE_PILOT_SETTINGS"]).read_text(encoding="utf-8")).get("model") or {}
        model = {k: _m[k] for k in ("auxiliary", "main", "engine", "claude_model") if k in _m}
        approved = json.loads(os.environ["JAVIS_RESONANCE_A5_APPROVED"])
    else:
        model = {"auxiliary": {"provider": "pilot-dry", "model": "fake"}, "main": {"provider": "pilot-dry",
                                                                                     "model": "fake"}}
        approved = {"aux": {"provider": "pilot-dry", "model": "fake"}}
    out_dir.mkdir(parents=True, exist_ok=True)
    assert not any(k in model for k in ("claude_auth", "anthropic_api_key")), "settings pilot không mang khoá API"
    (state / "settings.json").write_text(json.dumps({"model": model, "setup_done": True}, ensure_ascii=False),
                                         encoding="utf-8", newline="\n")
    (state / "usage.json").write_text(json.dumps({"days": {}, "total": {}}), encoding="utf-8", newline="\n")
    (state / "usage-events.jsonl").write_text("", encoding="utf-8", newline="\n")
    script = base / "dry-script.json"
    script.write_text(json.dumps(DRY_SCRIPTS.get(scen) or DRY_SCRIPTS["main_pass"], ensure_ascii=False),
                      encoding="utf-8", newline="\n")
    wall_s = 60 if (MODE == "dry" and scen == "timeout") else PHASE_B_WALL_S

    os.environ["JAVIS_STATE_DIR"] = str(state)
    os.environ["BRAINS_DIR"] = str(brains)
    import resonance as R  # noqa: E402  - sau khi đặt JAVIS_STATE_DIR
    import resonance_store as RS  # noqa: E402
    import sessions as SSm  # noqa: E402

    key = str(brain.resolve())
    owner = RS.Principal("owner", "owner", key)
    origin = f"http://127.0.0.1:{PORT}"
    pilot_vars = ("JAVIS_RESONANCE_TICK_PAUSED", "JAVIS_RESONANCE_CALL_CEILING", "JAVIS_CLAUDE_CLI", "JAVIS_CLAUDE_BIN",
                  "JAVIS_STATE_DIR", "BRAINS_DIR", "JAVIS_PORT", "JAVIS_A5_PILOT_MODE", "JAVIS_A5_PILOT_LEDGER",
                  "JAVIS_A5_PILOT_CAPS", "JAVIS_A5_PILOT_SCRIPT", "JAVIS_A5_PILOT_DRY_FORCE_REAL")
    env0 = {k: v for k, v in G.clean_env(dict(os.environ)).items() if k not in pilot_vars}
    fails, log = [], []
    rep = {"mode": MODE, "scenario": scen, "frozen_sha256": FROZEN_SHA, "caps": CAPS, "approved_max_calls": approved_max,
           "unit": "lượt engine cấp host (một lần dựng engine cho một lượt làm hay review)", "chat_turns": 0,
           "steps": {}}

    def check(name, cond, hard=False):
        print(("ok   " if cond else "FAIL ") + name)
        log.append({"check": name, "ok": bool(cond)})
        if not cond:
            fails.append(name)
            if hard:
                raise SystemExit(f"dừng: kiểm bắt buộc hỏng: {name}")
        return bool(cond)

    def store():
        return RS.GoalStore(state / "resonance.sqlite3")

    ledger_path = out_dir / "a5-pilot-ledger.json"
    if scen == "ledger_exists":
        ledger_path.write_text(json.dumps({"run_id": "trước", "caps": CAPS, "calls": [], "events": []}),
                               encoding="utf-8", newline="\n")

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
        """Không gọi model. Engine việc nền sẽ chạy đúng cấu hình đã duyệt; real: `claude auth status` bằng đúng binary,
        môi trường đã lọc là gói thuê bao gốc; settings không có apiKeyHelper hay env chọn nhà cung cấp; không có nguồn
        settings do quản trị đặt. Chỉ ghi siêu dữ liệu, không ghi khoá hay token."""
        eng = resolve_engines()
        out = {"ok": False, "why": "", "engines": {k: ({kk: (eng.get(k) or {}).get(kk) for kk in ("provider", "model")}
                                                       if isinstance(eng.get(k), dict) else eng.get(k))
                                                   for k in ("main", "aux", "claude_model")}, "approved": approved}
        ok_e, why_e = G.check_engines(eng, approved)
        if not ok_e:
            out["why"] = f"engine khác đã duyệt: {why_e}"
            return out
        if MODE == "dry":
            st = ({"loggedIn": True, "authMethod": "api_key", "apiProvider": "firstParty"} if scen == "auth"
                  else {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty",
                        "subscriptionType": "max"})
            ok, why = G.check_auth_status(st)
            out.update(ok=ok, why=why, auth={"dry_simulated": G.auth_metadata(st)})
            return out
        if (approved.get("aux") or {}).get("provider") not in ("anthropic-cli",):
            out["why"] = "pilot này chỉ hỗ trợ engine việc nền anthropic-cli (gói thuê bao)"
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
        if out["settings"]["risky"]:
            out["why"] = "nguồn settings có apiKeyHelper hay env chọn nhà cung cấp/khoá"
        elif out["managed_sources"]:
            out["why"] = "có nguồn settings do quản trị đặt; môi trường này pilot chưa hỗ trợ"
        else:
            out["ok"] = True
        return out

    def token_gate(cli: str) -> tuple:
        """Trước giai đoạn việc nền (không gọi model): hạn token gói thuê bao còn ít nhất TOKEN_MIN_S. Chỉ đọc hạn."""
        if MODE != "real":
            return True, ""
        import claude_token_gate
        exp = claude_token_gate.han_token()
        left = round(exp - time.time()) if exp else None
        rep["token_check"] = {"seconds_left": left}
        return (left is not None and left >= TOKEN_MIN_S), f"token còn {left} giây"

    class Server:
        def __init__(self, cli: str):
            self.n, self.proc, self.cli, self.started = 0, None, cli, []

        def start(self, phase: str, tick_paused: bool, caps: dict, ceiling: int, wait_s: int = 180) -> float:
            self.n += 1
            env = {**env0, "JAVIS_PORT": str(PORT), "JAVIS_STATE_DIR": str(state), "BRAINS_DIR": str(brains),
                   "JAVIS_REQUIRE_LOGIN": "0", "PYTHONUTF8": "1", "JAVIS_RESONANCE_CALL_CEILING": str(int(ceiling)),
                   "JAVIS_A5_PILOT_MODE": MODE, "JAVIS_A5_PILOT_LEDGER": str(ledger_path),
                   "JAVIS_A5_PILOT_CAPS": json.dumps(caps), "JAVIS_A5_PILOT_SCRIPT": str(script)}
            if scen == "tripwire":
                env["JAVIS_A5_PILOT_DRY_FORCE_REAL"] = "1"
            if self.cli:
                env["JAVIS_CLAUDE_CLI"] = self.cli
            if tick_paused:
                env["JAVIS_RESONANCE_TICK_PAUSED"] = "1"
            self.started.append({"n": self.n, "phase": phase, "tick_paused": tick_paused, "caps": caps,
                                 "call_ceiling": int(ceiling)})
            logf = open(base / f"server-{self.n}-{phase}.log", "w", encoding="utf-8")
            self.proc = subprocess.Popen([sys.executable, str(HERE.parent / "_a5_pilot_server.py")], cwd=str(ROOT),
                                         env=env, stdout=logf, stderr=subprocess.STDOUT,
                                         creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            import httpx
            t0 = time.time()
            while time.time() - t0 < wait_s:
                if self.proc.poll() is not None:
                    raise RuntimeError(f"server thoát sớm (server-{self.n}-{phase}.log)")
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

    def db_rows(sql, args=()):
        c = sqlite3.connect(Path(state / "resonance.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)
        try:
            c.row_factory = sqlite3.Row
            return [dict(r) for r in c.execute(sql, args).fetchall()]
        finally:
            c.close()

    def store_calls() -> int:
        r = db_rows("SELECT COALESCE(SUM(calls_used),0) AS n FROM goals")
        return int(r[0]["n"]) if r else 0

    def snapshot(gid: str) -> dict:
        """Ảnh chụp kho của mục tiêu (chỉ đọc): trạng thái, sổ vai, hành động, hàng review, lịch."""
        g = db_rows("SELECT status, run_state, block_reason, revision, calls_used, budget_calls, "
                    "lease_owner IS NOT NULL AND COALESCE(lease_until, 0) > ? AS leased FROM goals WHERE id=?",
                    (time.time(), gid))[0]
        tc = {r["role"]: {"cap": r["cap"], "used": r["used"]}
              for r in db_rows("SELECT role, cap, used FROM team_calls WHERE goal_id=?", (gid,))}
        acts = db_rows("SELECT id, kind, revision, seq, status, intent_json, receipt_json, created_at FROM actions "
                       "WHERE goal_id=? ORDER BY created_at, rowid", (gid,))
        for a in acts:
            a["intent"] = json.loads(a.pop("intent_json") or "{}")
            a["receipt"] = json.loads(a.pop("receipt_json") or "{}")
        revs = db_rows("SELECT id, revision, bundle_ref, accepted_ref, artifact_sha, snapshot_evidence_id, "
                       "reviewer_agent_key, "
                       "reviewer_config_version, action_id, seq, charged, status, verdict, reason_code, criteria_json, "
                       "fixes, evidence_id, created_at, finished_at FROM reviews WHERE goal_id=? ORDER BY created_at, "
                       "rowid", (gid,))
        wakes = db_rows("SELECT kind, due_at, reason FROM wakeups WHERE goal_id=?", (gid,))
        return {"goal": g, "team_calls": tc, "actions": acts, "reviews": revs, "wakes": wakes}

    srv = Server(resolve_cli() if MODE == "real" else "")
    t_start = time.time()
    gid = ""
    led = None
    try:
        # ───────────── Bước 0: nguồn, cổng chi phí, sổ, xác thực; TRƯỚC mọi server ─────────────
        # Nguồn: HEAD phải đúng SHA đã duyệt và cả checkout sạch (mã sản phẩm, chính bộ chạy, không file lạ). Real bắt
        # buộc; dry chỉ kiểm khi có SHA đã duyệt (ca `sha_mismatch`), còn lại ghi lại để đối chiếu.
        approved_sha = os.environ.get("JAVIS_RESONANCE_A5_APPROVED_SHA", "")
        pf = PL.preflight_source(Path(ROOT), approved_sha)
        rep["preflight"] = pf
        if MODE == "real" or approved_sha:
            if not check(f"nguồn: HEAD đúng SHA đã duyệt và checkout sạch ({pf['why'] or 'đạt'})", pf["ok"]):
                raise SystemExit("dừng trước mọi lượt: nguồn không phải bản đã duyệt hay checkout không sạch")
        if not check(f"cổng chi phí: trần tổng pilot ({CAPS['total']}) không vượt số lượt đã duyệt ({approved_max}) và "
                     f"đủ cho nhánh ngắn nhất ({MIN_CALLS})",
                     MIN_CALLS <= CAPS["total"] <= approved_max and CAPS["maker"] + CAPS["reviewer"] == CAPS["total"]):
            raise SystemExit("dừng trước mọi lượt: hạn mức đã duyệt nhỏ hơn trần pilot")
        if ledger_path.exists():
            raise SystemExit("dừng: sổ lượt pilot đã có từ lần chạy trước; không đặt lại")
        ledger_path.write_text(json.dumps({"run_id": f"a5-{int(time.time())}-{os.getpid()}", "caps": CAPS,
                                           "calls": [], "events": []}, ensure_ascii=False, indent=1),
                               encoding="utf-8", newline="\n")
        gate = auth_gate(srv.cli)
        rep["auth_gate"] = gate
        if not check(f"cổng xác thực và engine: đúng engine đã duyệt, gói thuê bao gốc ({gate.get('why') or 'đạt'})",
                     gate["ok"]):
            raise SystemExit("dừng trước mọi lượt: không chứng minh được đúng engine và chỉ dùng gói thuê bao")

        # ───────────── Bước 1 (server A, nhịp tạm dừng, trần kho 0, trần sổ 0): dựng đội và mục tiêu ─────────────
        rep["steps"]["start_A_s"] = round(srv.start("A", True, {"maker": 0, "reviewer": 0}, 0), 1)
        if scen == "early_crash":
            # Ca dry: bộ chạy lỗi giữa chừng, TRƯỚC bước lưu bằng chứng thông thường.
            raise RuntimeError("lỗi giả lập của bộ chạy trước bước lưu bằng chứng")
        for slug in (MAKER, REVIEWER):
            code, _b = http("POST", "/resonance/agents/toggle", json={"slug": slug, "enabled": True})
            check(f"chủ dự án bật Cộng hưởng cho {slug} qua API trang trợ lý", code == 200, hard=True)
        code, _b = http("POST", "/resonance/agents/reviewer", json={"slug": MAKER, "reviewer_slug": REVIEWER})
        check("chủ dự án chọn người review qua API ô Người review", code == 200, hard=True)
        st = store()
        mk, rv = st.agent(key, MAKER), st.agent(key, REVIEWER)
        ss = SSm.SessionStore(state / "conversations.db")
        sid = ss.create_session(brain=key, engine="pilot", model="pilot", channel=f"agent:{MAKER}")
        mid = ss.append_message(sid, "user", FROZEN["user_text"])
        ref = R.message_ref(sid, mid)
        g = asyncio.run(R.form_goal(ref, {
            "principal": RS.Principal("agent", mk["agent_key"], key), "brain_root": key, "session_id": sid,
            "message_id": mid, "user_text": FROZEN["user_text"], "constraints": [], "budget_calls": 4,
            "proposal": json.loads(json.dumps(FROZEN["proposal"])), "hold_until": None,
            "authority_seq": st.authority_seq(), "agent_key": mk["agent_key"], "agent_version": mk["config_version"]},
            R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "pilot_no_framer"}), budget=R.CallBudget(0),
                       store=st)))
        gid = g.id
        rep["goal_id"] = gid
        code, body = http("GET", f"/goals/{gid}")
        v = body.get("goal") or {}
        scv = v.get("scope") or {}
        code, ab = http("POST", f"/goals/{gid}/commands", json={
            "command": "approve_scope", "expected_revision": v.get("revision"),
            "request_id": str((scv.get("request") or {}).get("id") or ""), "path": scv.get("path"),
            "submission_id": "", "sha256": ""})
        rep["approve"] = {"code": code, "status": ab.get("status")}
        check("chủ cho phép phạm vi ghi qua API của nút trên thẻ (200)", code == 200, hard=True)
        tm = st.goal_team(owner, gid) or {}
        g1 = st.get(owner, gid)
        rep["team"] = {"reviewer_agent_key": tm.get("reviewer_agent_key"), "calls": tm.get("calls"),
                       "max_rounds": tm.get("max_rounds"), "budget_calls": g1.budget_calls}
        check("đội gắn trong giao dịch tạo: ghim mã bền của reviewer, 8 lượt chia 4/4, tối đa hai vòng",
              tm.get("reviewer_agent_key") == rv["agent_key"] and g1.budget_calls == 8 and tm.get("max_rounds") == 2
              and (tm.get("calls") or {}).get("maker", {}).get("cap") == 4
              and (tm.get("calls") or {}).get("reviewer", {}).get("cap") == 4, hard=True)
        check("phạm vi đã cấp, đúng file đích", st.scope_state(owner, gid).get("state") == "granted"
              and R._deliverable_rel(g1) == DELIV, hard=True)
        check("dựng xong: 0 lượt model (kho và sổ)", store_calls() == 0 and read_ledger(ledger_path)[0] is not None
              and not read_ledger(ledger_path)[0]["calls"], hard=True)
        check("chưa có file đích trước việc nền", not deliv.exists(), hard=True)
        srv.kill()

        # ───────────── Bước 2 (server B, nhịp chạy, trần kho = trần tổng pilot, trần vai) ─────────────
        if scen == "precondition":
            RS.GoalStore(state / "resonance.sqlite3").agent_set_enabled(owner, REVIEWER, False)
        if scen == "ledger_corrupt":
            ledger_path.write_text("{hỏng", encoding="utf-8", newline="\n")
        ag_m, ag_r = store().agent(key, MAKER), store().agent(key, REVIEWER)
        check("tiền điều kiện: hai trợ lý còn bật, đội còn ghim đúng reviewer, không kiểm nào hỏng",
              bool(ag_m and ag_m["enabled"] and ag_r and ag_r["enabled"]) and not fails
              and (store().goal_team(owner, gid) or {}).get("reviewer_agent_key") == rv["agent_key"], hard=True)
        ok, why = token_gate(srv.cli)
        check(f"cổng token trước việc nền ({why or 'đạt'})", ok, hard=True)
        before_files = G.snapshot_files(brain)
        # Ca dry `ledger_cap`: trần kho nâng lên trần sản phẩm (8) để lượt sửa thứ ba đi tới sổ pilot; chứng minh sổ tự
        # chặn trước khi dựng engine khi lớp trần kho không chặn. Real luôn dùng trần tổng của pilot.
        ceiling = 8 if (MODE == "dry" and scen == "ledger_cap") else CAPS["total"]
        # Từ đây một server có thể gọi model: mọi dừng sau mốc này là lỗi kỹ thuật, không phải "dừng ở cổng".
        rep["phase_B_started"] = True
        rep["steps"]["start_B_s"] = round(srv.start("B", False, {"maker": CAPS["maker"], "reviewer": CAPS["reviewer"]},
                                                    ceiling), 1)
        t0, last, trace, quiet_seen = time.time(), None, [], 0
        stop_why = "wall"
        while time.time() - t0 < wall_s:
            time.sleep(POLL_S)
            snap = snapshot(gid)
            sig = (snap["goal"]["status"], snap["goal"]["run_state"], snap["goal"]["block_reason"],
                   len(snap["actions"]), len(snap["reviews"]), snap["goal"]["calls_used"])
            if sig != last:
                trace.append({"t": round(time.time() - t0, 1), "status": sig[0], "run": sig[1], "reason": sig[2],
                              "actions": sig[3], "reviews": sig[4], "calls_used": sig[5]})
                last = sig
            lg, lerr = read_ledger(ledger_path)
            if lerr:
                stop_why = "ledger_" + lerr
                break
            lc = ledger_counts(lg)
            if lc["tripwire"]:
                stop_why = "tripwire"
                break
            # Host còn đang làm khi: có lượt `running`, mục tiêu ở `running`, hay một lần thức còn giữ khoá mục tiêu (ví dụ
            # vừa kết sổ lượt làm, chưa đăng bản và hẹn review: lịch thức tạm thời trống). Dry real-like tìm ra khe này:
            # trước đây bộ chạy dừng sớm ở đúng khe đó.
            busy = (any(a["status"] == "running" for a in snap["actions"]) or snap["goal"]["run_state"] == "running"
                    or bool(snap["goal"]["leased"]))
            if busy:
                quiet_seen = 0
                continue
            if snap["goal"]["status"] != "active":
                stop_why = "goal_" + snap["goal"]["status"]
                break
            if lc["not_ok"]:
                stop_why = "ledger_halted"
                break
            due = [float(w["due_at"]) for w in snap["wakes"] if w["kind"] == "work"]
            if not due or min(due) > time.time() + QUIET_S:
                # Im lặng phải đúng ở HAI lần quan sát liên tiếp, không dừng theo một ảnh chụp đơn lẻ.
                quiet_seen += 1
                if quiet_seen >= 2:
                    stop_why = "quiet"
                    break
            else:
                quiet_seen = 0
        rep["phase_B"] = {"stop": stop_why, "seconds": round(time.time() - t0, 1), "trace": trace}
        srv.kill()
        rep["brain_files_B"] = G.snapshot_diff(before_files, G.snapshot_files(brain))

        # ───────────── Bằng chứng và đối chiếu (chỉ đọc) ─────────────
        snap = snapshot(gid)
        lg, lerr = read_ledger(ledger_path)
        rep["ledger_status"] = lerr or "verified"
        check(f"sổ lượt pilot đọc được và đúng cấu trúc ({rep['ledger_status']})", lg is not None, hard=True)
        lc = ledger_counts(lg)
        rep["ledger_counts"] = lc
        check("dry: không chạm bẫy engine thật" if MODE == "dry" else "không chạm bẫy", lc["tripwire"] == 0, hard=True)
        tcm, tcr = snap["team_calls"].get("maker", {}), snap["team_calls"].get("reviewer", {})
        check(f"sổ pilot khớp sổ vai của kho: làm {lc['maker']}={tcm.get('used')}, review {lc['reviewer']}="
              f"{tcr.get('used')}, tổng {lc['total']}={snap['goal']['calls_used']}",
              lc["maker"] == tcm.get("used") and lc["reviewer"] == tcr.get("used")
              and lc["total"] == snap["goal"]["calls_used"])
        check(f"trong trần pilot: làm {lc['maker']}<={CAPS['maker']}, review {lc['reviewer']}<={CAPS['reviewer']}, "
              f"tổng {lc['total']}<={CAPS['total']}",
              lc["maker"] <= CAPS["maker"] and lc["reviewer"] <= CAPS["reviewer"] and lc["total"] <= CAPS["total"])
        works = [a for a in snap["actions"] if a["kind"] == "work"]
        reviews_a = [a for a in snap["actions"] if a["kind"] == "review"]
        check("mọi lượt làm do agent làm (mã ghim), có mốc gọi engine",
              all(a["intent"].get("agent_key") == mk["agent_key"] and a["intent"].get("role") == "maker"
                  and a["intent"].get("engine_at") for a in works if a["status"] != "cancelled"))
        check("mọi lượt review do đúng reviewer đã ghim (mã bền), không phải agent làm, có mốc gọi engine",
              all(a["intent"].get("reviewer_agent_key") == rv["agent_key"] and a["intent"].get("role") == "reviewer"
                  and a["intent"].get("engine_at") for a in reviews_a if a["status"] != "cancelled")
              and rv["agent_key"] != mk["agent_key"])
        rows = snap["reviews"]
        check("mỗi lượt review tính (charged=1) ứng với đúng một lượt reviewer trong sổ",
              sum(1 for r in rows if r["charged"] == 1) == lc["reviewer"])
        # Đúng hash và revision: bộ ghim mang đúng revision, mốc đăng, hash và mã reviewer của hàng; hash đó là bytes (đã
        # chuẩn hoá như khi đăng) của một đầu ra lượt làm thành công. Ảnh chụp reviewer đọc kiểm riêng ở bước lưu bằng chứng.
        out_root = Path(g1.output_root)
        maker_shas = {_sha(R._norm_bytes((out_root / f"{a['id']}.md").read_text(encoding="utf-8"))[0])
                      for a in snap["actions"] if a["kind"] == "work" and a["status"] == "succeeded"
                      and (out_root / f"{a['id']}.md").is_file()}
        bundle_ok = True
        for r in rows:
            parts = str(r["bundle_ref"]).split(":")
            if not (len(parts) == 7 and parts[1] == str(r["revision"]) and parts[2] == r["accepted_ref"]
                    and parts[3] == r["artifact_sha"] and parts[5] == rv["agent_key"]
                    and r["reviewer_agent_key"] == rv["agent_key"] and r["artifact_sha"] in maker_shas):
                bundle_ok = False
        # Mọi hàng review có mặt phải đúng bộ ghim; có hàng review thì phải có lượt làm thành công trước đó. Số hàng review
        # đúng của từng nhánh (kể cả nhánh không có review, như `maker_not_met`) do `decide_acceptance` kiểm.
        check("mỗi lượt review đọc đúng bản đã tiếp nhận: revision, hash bytes đầu ra của lượt làm, mã reviewer",
              bundle_ok and (not rows or bool(works and works[0]["status"] == "succeeded")))
        valid = [r for r in rows if r["status"] in ("done", "failed") and r["reason_code"] not in ("stale",
                                                                                                    "review_mismatch")]
        verdicts = [r["verdict"] for r in valid]
        branch = classify(snap["goal"]["status"], verdicts, [a["status"] for a in works], lc["refused"],
                          snap["goal"]["block_reason"], reviewer_failed="reviewer" in lc["not_ok_roles"])
        rep["branch"] = branch
        if scen == "ledger_cap":
            check("sổ pilot chặn lượt sửa thứ ba TRƯỚC khi dựng engine (cap_maker), host hoàn lượt (làm dùng 2)",
                  "cap_maker" in lc["refused"] and tcm.get("used") == 2
                  and snap["goal"]["block_reason"] == "engine_blocked")
        rep["verdicts"] = verdicts
        if any(v == "needs_changes" for v in verdicts):
            fix = [a for a in works[1:]]
            check("sau kết luận cần sửa: vai làm có lượt sửa riêng (lượt làm sau hàng review đó)",
                  bool(fix) and fix[0]["created_at"] >= next(r["created_at"] for r in valid
                                                             if r["verdict"] == "needs_changes"))
        if snap["goal"]["status"] == "succeeded":
            last_pass = [r for r in valid if r["verdict"] == "pass"]
            check("chốt đạt sau review pass: file đích đúng bytes bản được review pass, cùng revision",
                  bool(last_pass) and _sha_file(deliv) == last_pass[-1]["artifact_sha"]
                  and last_pass[-1]["revision"] == snap["goal"]["revision"])
        check("ngoài file đích, không file nào trong brain bị đổi; ghi chú cũ còn nguyên",
              set((rep["brain_files_B"] or {}).get("changed", []) + (rep["brain_files_B"] or {}).get("added", []))
              <= {DELIV} and not (rep["brain_files_B"] or {}).get("removed") and _sha_file(keep) == keep_sha)
        if scen == "missing_output" and works:
            # Ca dry: đầu ra lượt làm không còn ở chỗ host ghi (đổi tên, không xoá) trước bước lưu.
            src0 = out_root / f"{works[0]['id']}.md"
            if src0.is_file():
                os.replace(src0, src0.with_name(src0.name + ".moved"))
        # Lưu nguyên vẹn đầu ra của từng lượt làm và từng lượt review (đọc bằng chứng đã mã hoá của host).
        saved = []
        for i, a in enumerate([a for a in works if a["status"] == "succeeded"], 1):
            saved.append({"role": "maker", "n": i, "action_id": a["id"],
                          **G.preserve_artifact(out_root / f"{a['id']}.md", out_dir / f"a5-maker-{i}.md")})
        try:
            import context_runtime
            import evidence_store
            es = evidence_store.EvidenceStore(context_runtime.get_runtime())
            for i, r in enumerate([r for r in rows if r["evidence_id"]], 1):
                txt = es.read_artifact(r["evidence_id"])
                p = out_dir / f"a5-reviewer-{i}.txt"
                p.write_text(txt, encoding="utf-8", newline="\n")
                saved.append({"role": "reviewer", "n": i, "review_id": r["id"], "ok": True, "sha256": _sha(txt)})
            # Ảnh chụp mà lượt review đã đọc (bằng chứng host lưu khi tiếp nhận): băm lại phải đúng hash của hàng.
            snap_ok = [_sha(R._norm_bytes(es.read_artifact(r["snapshot_evidence_id"]))[0]) == r["artifact_sha"]
                       for r in rows if r["status"] != "cancelled"]
            rep["snapshot_hash_ok"] = snap_ok
            check("ảnh chụp mỗi lượt review đã đọc băm lại đúng hash bản đã tiếp nhận", bool(snap_ok) == bool(
                [r for r in rows if r["status"] != "cancelled"]) and all(snap_ok))
        except Exception as e:  # noqa: BLE001
            saved.append({"role": "reviewer", "ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"})
        if deliv.is_file():
            saved.append({"role": "deliverable", **G.preserve_artifact(deliv, out_dir / "a5-deliverable-final.md")})
        rep["saved"] = saved
        check("đầu ra mọi lượt làm, mọi lượt review và file đích lưu nguyên vẹn ra hồ sơ",
              all(s.get("ok") for s in saved) and sum(1 for s in saved if s["role"] == "reviewer")
              == sum(1 for r in rows if r["evidence_id"]))
        rep["store_B"] = {"goal": snap["goal"], "team_calls": snap["team_calls"],
                          "reviews": [{k: r[k] for k in ("seq", "status", "verdict", "reason_code", "charged",
                                                          "artifact_sha", "revision", "fixes")} for r in rows],
                          "actions": [{"kind": a["kind"], "status": a["status"],
                                       "error": a["receipt"].get("error_code") or a["receipt"].get("not_run_reason"),
                                       "engine": a["receipt"].get("engine")} for a in snap["actions"]]}

        # ───────────── Bước 3 (server C, nhịp chạy, trần 0): dựng lại không gọi thêm ─────────────
        n_calls, n_events = lc["total"], len(lg["events"])
        n_actions, n_reviews = len(snap["actions"]), len(rows)
        rep["steps"]["start_C_s"] = round(srv.start("C", False, {"maker": 0, "reviewer": 0}, store_calls()), 1)
        time.sleep(RESTART_WAIT_S)
        lg2, lerr2 = read_ledger(ledger_path)
        snap2 = snapshot(gid)
        new_events = (lg2 or {}).get("events", [])[n_events:]
        rep["restart"] = {"new_ledger_events": new_events, "ledger_status": lerr2 or "verified",
                          "actions": len(snap2["actions"]) - n_actions, "reviews": len(snap2["reviews"]) - n_reviews}
        rep["restart"]["ok"] = check(
            "dựng lại: không lượt nào được gọi hay thử gọi thêm (sổ, hành động, hàng review không đổi)",
            lg2 is not None and len(lg2["calls"]) == n_calls and not new_events
            and len(snap2["actions"]) == n_actions and len(snap2["reviews"]) == n_reviews)
        if snap2["goal"]["status"] == "active":
            code, _b = http("POST", f"/goals/{gid}/commands", json={"command": "pause",
                                                                     "expected_revision": snap2["goal"]["revision"]})
            check("kết thúc: tạm dừng mục tiêu còn mở qua API, không còn việc nền", code == 200)
        rep["final"] = {"status": snapshot(gid)["goal"]}
        if scen == "ledger_lost_end":
            # Ca dry: sổ mất ngay trước lần đọc cuối (đổi tên, không xoá).
            os.replace(ledger_path, ledger_path.with_name(ledger_path.name + ".lost"))
    except SystemExit as e:
        print(f"DỪNG: {e}")
        rep["stopped"] = str(e)
    except Exception as e:  # noqa: BLE001
        check(f"bộ chạy không lỗi ({type(e).__name__}: {e})", False)
    finally:
        srv.kill()
        # Lần đọc sổ CUỐI quyết định: thiếu, hỏng hay lệch là chưa xác minh (không bao giờ là 0 lượt).
        lg, lerr = read_ledger(ledger_path)
        rep["ledger"] = lg
        rep["ledger_status"] = lerr or "verified"
        lc = ledger_counts(lg) if lg else None
        rep["ledger_final_counts"] = lc
        rep["model_turns"] = {"chat": 0,
                              "background_real": (lc["total"] if lc else None) if MODE == "real" else 0,
                              "background_simulated": (lc["total"] if lc else None) if MODE == "dry" else 0}
        # Sổ lượt engine của server sandbox (usage.json): phải đọc được và khớp nhau ở CẢ HAI chế độ; dry còn phải bằng 0.
        try:
            usage = json.loads((state / "usage.json").read_text(encoding="utf-8"))
            total = usage.get("total") if isinstance(usage, dict) else None
            if not isinstance(total, dict) or not all(isinstance(v, dict) and "turns" in v and type(v["turns"]) is int
                                                      and v["turns"] >= 0 for v in total.values()):
                raise ValueError("usage.json sai cấu trúc")
            turns = sum(v["turns"] for v in total.values())
            events = [ln for ln in (state / "usage-events.jsonl").read_text(encoding="utf-8").splitlines()
                      if ln.strip()]
            if len(events) != turns:
                raise ValueError(f"hai sổ lệch nhau: {turns} lượt, {len(events)} dòng")
            rep["engine_turns_logged"], rep["engine_turns_status"] = turns, "verified"
        except (OSError, ValueError) as e:
            rep["engine_turns_logged"] = None
            rep["engine_turns_status"] = f"unverified: {type(e).__name__}: {str(e)[:120]}"
        if MODE == "dry":
            check(f"dry: đã xác minh server không ghi lượt engine thật nào ({rep['engine_turns_status']})",
                  rep["engine_turns_logged"] == 0)
        # Bảo toàn bằng chứng (mọi server đã dừng): kho, log đã che khoá, sổ usage, brain tạm, ra thư mục MỚI trong hồ sơ.
        # Kho bắt buộc khi đã có server; log của mọi server đã dựng cũng bắt buộc.
        required = (["resonance.sqlite3"] if rep.get("goal_id") else []) + \
            [f"server-{x['n']}-{x['phase']}.log" for x in srv.started]
        try:
            pres = PL.preserve_sandbox(base, out_dir, required=required,
                                       fault=(lambda name: name == "resonance.sqlite3") if scen == "save_error" else None)
        except Exception as e:  # noqa: BLE001
            pres = {"ok": False, "dest": "", "items": [], "error": f"{type(e).__name__}: {str(e)[:200]}"}
        rep["preserve"] = {"ok": pres["ok"], "items": pres["items"], "error": pres.get("error", ""),
                           "dest": Path(pres["dest"]).name if pres.get("dest") else ""}
        rep["servers"] = srv.started
        rep["seconds_total"] = round(time.time() - t_start, 1)
        rep["checks"] = log
        acc, why = PL.decide_acceptance(rep, fails, MODE)
        rep["acceptance"], rep["acceptance_why"] = acc, why
        try:
            rep["commit"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True,
                                           timeout=10).stdout.strip()
        except Exception:  # noqa: BLE001
            rep["commit"] = ""
        delete = PL.may_delete_sandbox(MODE, acc, pres, base, out_dir)
        # Ghi hồ sơ cuối là một phần của kết luận (review cổng vòng 2): file đường khôi phục trước, báo cáo JSON sau cùng.
        # Lần ghi bắt buộc nào lỗi thì kết luận thành technical_failed, sandbox giữ lại; dòng A5_PILOT, mã thoát và báo
        # cáo (nếu ghi được) cùng một kết luận.
        delete = PL.finalize_record(rep, MODE, scen, base, out_dir, pres, delete, lc, fault=PL.dry_fault(MODE, scen))
        if delete:
            shutil.rmtree(base, ignore_errors=True)
    return PL.EXIT_CODES.get(rep["acceptance"], 1)


# ───────────── dry: mọi ca, mỗi ca một tiến trình con; real: đúng một ca chính ─────────────

DRY_CASES = {
    # ca: (biến môi trường thêm, kết luận, nhánh, (lượt làm, lượt review) trong sổ cuối, câu phải có trong output)
    # Kỹ thuật đạt, mục tiêu chốt: chờ duyệt nội dung.
    "main_pass": ({}, "pending_content_review", "pass_first", (1, 1), "chốt đạt sau review pass"),
    "main_fix": ({}, "pending_content_review", "one_fix_then_pass", (2, 2), "vai làm có lượt sửa riêng"),
    # Kỹ thuật đạt, nhánh nghiệp vụ chưa đạt (đã định nghĩa).
    "fix_cap": ({}, "business_incomplete", "pilot_cap_after_two_reviews", (2, 2), "dựng lại: không lượt nào"),
    "ledger_cap": ({}, "business_incomplete", "pilot_cap_after_two_reviews", (2, 2),
                   "ok   sổ pilot chặn lượt sửa thứ ba"),
    "review_unknown": ({}, "business_incomplete", "review_unknown", (1, 1), "dựng lại: không lượt nào"),
    "maker_not_met": ({}, "business_incomplete", "maker_not_met", (1, 0), "dựng lại: không lượt nào"),
    # Lỗi kỹ thuật qua đường điều phối thật (engine giả): technical_failed, giữ nhánh, giữ sandbox.
    "maker_error": ({}, "technical_failed", "maker_error", (1, 0), "A5_PILOT_KEPT"),
    "reviewer_error": ({}, "technical_failed", "reviewer_error", (1, 1), "A5_PILOT_KEPT"),
    "final_is_error": ({}, "technical_failed", "maker_error", (1, 0), "A5_PILOT_KEPT"),
    "timeout": ({}, "technical_failed", "maker_error", (1, 0), "A5_PILOT_KEPT"),
    "missing_output": ({}, "technical_failed", "pass_first", (1, 1), "FAIL đầu ra mọi lượt làm"),
    "ledger_lost_end": ({}, "technical_failed", "pass_first", (None, None), "A5_PILOT_KEPT"),
    "save_error": ({}, "technical_failed", "pass_first", (1, 1), "A5_PILOT_KEPT"),
    "early_crash": ({}, "technical_failed", None, (0, 0), "FAIL bộ chạy không lỗi"),
    "ledger_corrupt": ({}, "technical_failed", None, (None, None), "FAIL sổ lượt pilot đọc được"),
    # Lỗi ghi hồ sơ cuối (review cổng vòng 2), qua run_case thật: kết quả đạt, nghiệp vụ chưa đạt và lỗi kỹ thuật vốn có
    # đều thành technical_failed, mã thoát 1, sandbox giữ; nhánh giữ nguyên.
    "report_fault": ({}, "technical_failed", "pass_first", (1, 1), "KHÔNG GHI ĐƯỢC HỒ SƠ CUỐI"),
    "recovery_fault": ({}, "technical_failed", "review_unknown", (1, 1), "KHÔNG GHI ĐƯỢC HỒ SƠ CUỐI"),
    "report_fault_technical": ({}, "technical_failed", "maker_error", (1, 0), "KHÔNG GHI ĐƯỢC HỒ SƠ CUỐI"),
    # Bẫy: sổ đã giữ chỗ TRƯỚC khi dựng (bảo thủ) nên có một dòng `not_built`; không có lời gọi nào tới engine.
    "tripwire": ({}, "technical_failed", None, (1, 0), "FAIL dry: không chạm bẫy"),
    # Dừng ở cổng, trước mọi server có thể gọi model.
    "cost": ({"JAVIS_RESONANCE_A5_MAX_CALLS": "3"}, "stopped", None, None, "dừng trước mọi lượt: hạn mức"),
    "auth": ({}, "stopped", None, None, "dừng trước mọi lượt: không chứng minh"),
    "ledger_exists": ({}, "stopped", None, None, "sổ lượt pilot đã có từ lần chạy trước"),
    "precondition": ({}, "stopped", None, None, "kiểm bắt buộc hỏng: tiền điều kiện"),
    "sha_mismatch": ({"JAVIS_RESONANCE_A5_APPROVED_SHA": "0" * 40}, "stopped", None, None,
                     "dừng trước mọi lượt: nguồn"),
}
# Bảo toàn bằng chứng phải đạt ở mọi ca, trừ ca chèn lỗi lúc lưu.
PRESERVE_FAILS = {"save_error"}


def _extra_checks(name: str, case_dir: Path, kept: str) -> list:
    """Kiểm riêng của các ca sự cố: nguồn còn nguyên, file hỏng không bị ghi đè, có đường khôi phục."""
    def isfile(p):
        return os.path.isfile(PL._xp(p))

    bad = []
    if name == "ledger_corrupt":
        with open(PL._xp(case_dir / "a5-pilot-ledger.json"), "rb") as f:
            if f.read() != "{hỏng".encode("utf-8"):
                bad.append("sổ hỏng bị ghi đè")
    if name == "ledger_lost_end" and not isfile(case_dir / "a5-pilot-ledger.json.lost"):
        bad.append("sổ đổi tên không còn")
    if name in ("save_error", "maker_error", "timeout", "early_crash", "ledger_corrupt", "ledger_lost_end",
                "report_fault", "recovery_fault", "report_fault_technical"):
        if not kept or not os.path.isdir(PL._xp(kept)):
            bad.append("sandbox không được giữ")
        elif name != "early_crash" and not isfile(Path(kept) / "state" / "resonance.sqlite3"):
            bad.append("kho gốc trong sandbox không còn")
        # Ca chặn chính file khôi phục: đường sandbox phải nằm trên stdout/stderr (câu "KHÔNG GHI ĐƯỢC HỒ SƠ CUỐI").
        if name != "recovery_fault" and not isfile(case_dir / "a5-pilot-recovery.txt"):
            bad.append("thiếu đường khôi phục")
    if name not in PRESERVE_FAILS and name not in ("cost", "auth", "ledger_exists", "sha_mismatch"):
        dest = case_dir / "sandbox"
        logs = os.listdir(PL._xp(dest / "logs")) if os.path.isdir(PL._xp(dest / "logs")) else []
        if not any(x.startswith("server-") for x in logs):
            bad.append("bản sao bằng chứng thiếu log server")
        if name != "early_crash" and not isfile(dest / "state" / "resonance.sqlite3"):
            bad.append("bản sao bằng chứng thiếu kho")
    return bad


if SCEN:
    sys.exit(run_case(SCEN))
if MODE == "real":
    sys.exit(run_case("main"))

only = [x for x in os.environ.get("JAVIS_RESONANCE_A5_DRY_ONLY", "").split(",") if x]
dry_dir = Path(os.environ.get("JAVIS_RESONANCE_A5_DRY_DIR") or tempfile.mkdtemp(prefix="rsa5dry-"))
os.environ["JAVIS_RESONANCE_A5_DRY_DIR"] = str(dry_dir)
bad = []
for name, (extra, want, want_branch, want_calls, needle) in DRY_CASES.items():
    if only and name not in only:
        continue
    case_dir = dry_dir / name
    if case_dir.exists():
        print(f"FAIL ca {name}: thư mục hồ sơ đã có ({case_dir}); không ghi đè")
        bad.append(name)
        continue
    env = {**os.environ, "JAVIS_RESONANCE_A5_SCENARIO": name, "PYTHONIOENCODING": "utf-8", **extra}
    env.pop("JAVIS_RESONANCE_A5_OUT", None)
    if "JAVIS_RESONANCE_A5_APPROVED_SHA" not in extra:
        env.pop("JAVIS_RESONANCE_A5_APPROVED_SHA", None)
    cp = subprocess.run([sys.executable, str(HERE)], cwd=str(ROOT), env=env, capture_output=True, text=True,
                        encoding="utf-8", timeout=1800)
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / f"a5-pilot-dry-{name}.txt").write_text(cp.stdout + cp.stderr[-4000:], encoding="utf-8", newline="\n")
    line = next((x for x in cp.stdout.splitlines() if x.startswith("A5_PILOT ")), "")
    kept = next((x[len("A5_PILOT_KEPT "):].strip() for x in cp.stdout.splitlines()
                 if x.startswith("A5_PILOT_KEPT ")), "")
    got, pres_ok, lcg = {}, None, None
    if line:
        head, _s, rest = line[len("A5_PILOT "):].partition(" PRESERVE ")
        pres, _s, tail = rest.partition(" LEDGER ")
        got, pres_ok, lcg = json.loads(head), json.loads(pres or "null"), json.loads(tail or "null")
    calls = (lcg["maker"], lcg["reviewer"]) if lcg else (None, None)
    extra_bad = _extra_checks(name, case_dir, kept) if line else ["không có dòng A5_PILOT"]
    # Các kênh kết quả phải nhất quán (review cổng vòng 2): mã thoát đúng hợp đồng của kết luận; báo cáo JSON bắt buộc có
    # (trừ ca chèn lỗi ghi báo cáo, khi đó báo cáo KHÔNG được có) và nói cùng kết luận, nhánh, trạng thái giữ sandbox với
    # dòng A5_PILOT; dòng KEPT có đúng khi sandbox được giữ.
    want_exit = PL.EXIT_CODES.get(want, 1)
    if cp.returncode != want_exit:
        extra_bad.append(f"mã thoát {cp.returncode}, hợp đồng {want_exit}")
    rpath = case_dir / f"a5-pilot-dry-{name}.json"
    if PL.dry_fault("dry", name) == "report":
        if os.path.exists(PL._xp(rpath)) or got.get("report_saved") is not False:
            extra_bad.append("ca lỗi ghi báo cáo mà vẫn có báo cáo hay report_saved khác false")
    elif not os.path.isfile(PL._xp(rpath)):
        extra_bad.append("thiếu báo cáo JSON bắt buộc")
    else:
        with open(PL._xp(rpath), "rb") as f:
            saved = json.loads(f.read().decode("utf-8"))
        if (saved.get("acceptance"), saved.get("branch"), saved.get("sandbox_kept")) != (
                got.get("acceptance"), got.get("branch"), got.get("sandbox_kept")) or got.get("report_saved") is not True:
            extra_bad.append("báo cáo JSON khác dòng A5_PILOT")
    if bool(kept) != bool(got.get("sandbox_kept")):
        extra_bad.append("dòng KEPT không khớp sandbox_kept")
    ok = (got.get("acceptance") == want and needle in cp.stdout and got.get("engine_turns_logged") == 0
          and (got.get("model_turns") or {}).get("background_real", 1) == 0
          and (want_branch is None or got.get("branch") == want_branch)
          and (want_calls is None or calls == want_calls)
          and pres_ok is (name not in PRESERVE_FAILS) and not extra_bad)
    print(("ok   " if ok else "FAIL ") + f"ca {name}: kết luận {got.get('acceptance')} (mong {want}), nhánh "
          f"{got.get('branch')} (mong {want_branch}), sổ (làm, review) {calls} (mong {want_calls}), bảo toàn "
          f"{pres_ok}, sandbox giữ {bool(kept)}, lượt engine server ghi {got.get('engine_turns_logged')}"
          + (f", lỗi: {extra_bad}" if extra_bad else ""))
    if not ok:
        bad.append(name)
        print("\n".join("    " + x for x in cp.stdout.splitlines()[-30:]))
    elif kept and pres_ok and Path(kept).is_dir() and not Path(kept).resolve().is_relative_to(case_dir.resolve()):
        # Ca đúng kỳ vọng mà bằng chứng ĐÃ được chép đủ vào hồ sơ của ca: dọn bản sandbox trùng. Ca bảo toàn lỗi giữ lại.
        shutil.rmtree(kept, ignore_errors=True)
    if got.get("engine_turns_logged") != 0 or (got.get("model_turns") or {}).get("background_real", 1) != 0:
        print(f"DỪNG CẢ ĐỢT: ca {name} có lượt engine {got.get('engine_turns_logged')!r} "
              f"({got.get('engine_turns_status') or 'không có báo cáo'}); không mở ca kế tiếp, không thử lại.")
        if name not in bad:
            bad.append(name)
        break
print(f"\nhồ sơ dry: {dry_dir}")
if bad:
    print(f"\n{len(bad)} FAIL:", bad)
    sys.exit(1)
print("\nOK")
