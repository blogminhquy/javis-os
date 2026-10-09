"""Resonance A3: pilot làn M với engine thật, cổng tối đa 5 lượt model thật ở biên gọi engine.

    JAVIS_RESONANCE_A3_PILOT=dry  python tests/python/test_resonance_a3_pilot.py      # KHÔNG gọi model, mọi nhánh
    JAVIS_RESONANCE_A3_PILOT=real JAVIS_RESONANCE_PILOT_SETTINGS=<settings.json thật> \\
        JAVIS_RESONANCE_A3_OUT=<thư mục báo cáo> python tests/python/test_resonance_a3_pilot.py   # cần người dùng duyệt

Không đặt biến thì bỏ qua (CI và tests/run.py không gọi gì). Gói và review: exports/reviews/A3-pilot-approval-request.md,
PR-598-A3-ui-224a109a-review.md (ngoài git).

Kịch bản (đóng băng, mục FROZEN dưới đây):
- Brain và state tạm. Trợ lý tạm bật qua kho. Mục tiêu lập bằng đề xuất host dựng sẵn (không qua chat), một tiêu chí
  host chấm ba ý; revision 2 là lời người dùng nói lại cùng ba ý, chữ khác (tập giữ riêng của phép thử).
- Ba lượt làm trước bế tắc chạy bằng ENGINE GIẢ `fake-seed`: tính vào `calls_used` của mục tiêu nhưng không phải lượt
  model. Dừng ở bài học `trial_pending`, kiểm tiền điều kiện, rồi mới đổi sang engine qua cổng.
- Sau đó lịch nền chạy như sản phẩm: phép thử 2 tình huống x 2 cách làm (4 lượt), nếu `eligible` thì một lượt làm
  sản phẩm bằng lượt đã giữ. Không đổi luật M5 hay oracle để ép kết quả.

Hai lớp trần, khác nhau và không thay nhau:
- Trần KHO `JAVIS_RESONANCE_CALL_CEILING=8`: đếm mọi lượt trong kho tạm (3 lượt giả + tối đa 5 lượt sau đó), giữ qua
  khởi động lại. Không phải hạn mức model thật.
- Cổng LƯỢT THẬT (RealCallGate): tối đa 5 lời gọi engine thật, ghi sổ xuống đĩa TRƯỚC mỗi lời gọi, không đặt lại, không
  hoàn. Lời gọi lỗi, hết giờ, bị huỷ, đầu ra hỏng, gọi công cụ, hay token sắp hết hạn: cổng ĐÓNG, mọi lời gọi sau bị
  từ chối trước khi tới engine (host thấy engine chưa sẵn sàng, không tính lượt). Tiến trình chết giữa lời gọi: dòng
  `reserved` còn trong sổ, vẫn tính là có thể đã gọi.

Mỗi kịch bản chạy hai tiến trình: giai đoạn 1 (dựng, gieo, chạy tới khi xong hay cổng đóng), giai đoạn 2 (mở lại kho
bằng tiến trình mới, cổng ĐÓNG hẳn, đối soát hai lượt). Dry chạy mọi nhánh: thắng, no_improvement, regression, unknown,
lỗi engine ở lượt đầu, lượt cuối phép thử và lượt sản phẩm, hết giờ, token sắp hết hạn, tiến trình chết giữa lời gọi,
lỗi lưu trữ, trần cổng giữa phép thử, trần kho thiếu. Real chạy đúng một kịch bản `real`.
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

MODE = os.environ.get("JAVIS_RESONANCE_A3_PILOT", "").strip().lower()
CHILD = "--child" in sys.argv
if MODE not in ("dry", "real", "preflight") and not CHILD:
    print("pilot A3: bỏ qua (đặt JAVIS_RESONANCE_A3_PILOT=dry hoặc real để chạy)")
    print("\nOK")
    sys.exit(0)

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import _e2e_pilot_guard as G  # noqa: E402

REAL_LIMIT = 5
STORE_CEILING = 8
TOKEN_MIN_S = 600
REAL_WALL_S = 300
SLUG = "tro-ly-ghi-chu"

# ───────────── Đầu vào ĐÓNG BĂNG: không chọn dữ liệu lúc chạy ─────────────
FROZEN = {
    "agent_md": ("---\nname: Trợ lý ghi chú\nrole: Soạn ghi chú tổng hợp\n---\n"
                 "Bạn soạn ghi chú tổng hợp ngắn gọn theo lời chủ dặn.\n"),
    "deliverable": "Inbox/tong-hop.md",
    "user_1": ("(Dữ liệu mô phỏng để thử nghiệm.) Em viết giúp anh một ghi chú tổng hợp ở Inbox/tong-hop.md, nhắc đủ "
               "ba việc tuần này: nộp báo cáo quý cho phòng kế toán, gọi thợ bảo trì máy lạnh ở kho, và gia hạn hợp "
               "đồng thuê kho trước cuối tháng."),
    "user_2": ("(Dữ liệu mô phỏng để thử nghiệm.) Anh nói lại cho rõ: ghi chú Inbox/tong-hop.md là để cả nhóm đọc "
               "đầu tuần sau, vẫn phải đủ ba việc là báo cáo quý, máy lạnh ở kho và hợp đồng thuê kho, mỗi việc "
               "một dòng có người phụ trách."),
    "understanding_1": "Ghi chú tổng hợp ba việc tuần này trong Inbox",
    "understanding_2": "Ghi chú tổng hợp ba việc cho cả nhóm đọc đầu tuần sau",
    "criteria": [{"description": "Ghi chú nhắc đủ ba việc", "evaluator": "artifact_contract",
                  "params": {"path": "Inbox/tong-hop.md",
                             "must_contain": ["báo cáo quý", "máy lạnh", "hợp đồng thuê kho"]}}],
    "budget_calls": 9,
    "baseline": "work.v1",
    "candidate": "work.checklist.v1",
    "seed_output": "# Ghi chú tổng hợp\n\n- Nộp báo cáo quý cho phòng kế toán.\n",
}


def _sha(s) -> str:
    if not isinstance(s, (bytes, str)):
        s = json.dumps(s, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(s.encode("utf-8") if isinstance(s, str) else s).hexdigest()


# ───────────── Cổng lượt thật ─────────────

class RealCallGate:
    """Sổ lời gọi engine thật, ghi xuống đĩa (os.replace + fsync) TRƯỚC khi gọi. Đọc lại từ file ở mỗi lần hỏi, nên
    tiến trình mới (khởi động lại) thấy đúng các lời gọi cũ, kể cả dòng `reserved` của tiến trình đã chết."""

    def __init__(self, path: Path, limit: int, token_check=None, closed: str = ""):
        self.path, self.limit, self.token_check, self.closed = Path(path), int(limit), token_check, closed
        self.refusals, self.last_check = [], ""

    def state(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - chưa có file: chưa gọi lần nào
            return {"limit": self.limit, "calls": [], "halted": ""}

    def _write(self, st: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(st, ensure_ascii=False, indent=1))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def calls(self) -> list:
        return list(self.state().get("calls") or [])

    def halted(self) -> str:
        st = self.state()
        if st.get("halted"):
            return st["halted"]
        if any(c.get("status") == "reserved" for c in st.get("calls") or []):
            # Dòng giữ chỗ chưa chốt mà tiến trình hiện tại không gọi: tiến trình trước đã chết giữa lời gọi.
            return "reserved_without_outcome"
        return ""

    def allow(self) -> tuple:
        if self.closed:
            return False, self.closed
        h = self.halted()
        if h:
            return False, f"halted: {h}"
        if len(self.calls()) >= self.limit:
            return False, "limit"
        if self.token_check:
            ok, why = self.token_check()
            if not ok:
                self.halt(f"token: {why}")
                return False, f"token: {why}"
            self.last_check = why
        return True, ""

    def refuse(self, why: str) -> None:
        self.refusals.append(why)

    def reserve(self, label: str, prompt: str) -> int:
        st = self.state()
        st.setdefault("calls", []).append({"n": len(st["calls"]) + 1, "label": label, "status": "reserved",
                                           "prompt_sha256": _sha(prompt), "started_at": time.time(),
                                           "preflight": self.last_check})
        st["limit"] = self.limit
        self._write(st)
        return len(st["calls"])

    def settle(self, n: int, status: str, **kw) -> None:
        st = self.state()
        for c in st.get("calls") or []:
            if c["n"] == n:
                c.update(status=status, finished_at=time.time(), **kw)
        self._write(st)

    def halt(self, why: str) -> None:
        st = self.state()
        if not st.get("halted"):
            st["halted"] = why
            self._write(st)


class GatedEngine:
    """Bọc engine thật (hay engine dry mang vai engine thật). Hỏi cổng ở `is_available` VÀ ngay trước lời gọi."""

    def __init__(self, inner, gate: RealCallGate, save_dir: Path, label: str, max_chars: int):
        self.inner, self.gate, self.save_dir, self.label, self.max_chars = inner, gate, Path(save_dir), label, max_chars
        self.max_wall_s = None

    def is_available(self):
        ok, why = self.gate.allow()
        if not ok:
            self.gate.refuse(why)
            return False
        return self.inner.is_available()

    async def query(self, prompt):
        ok, why = self.gate.allow()
        if not ok:
            self.gate.refuse(why)
            yield {"type": "error", "content": f"pilot gate từ chối trước lời gọi: {why}"}
            return
        try:
            self.inner.max_wall_s = self.max_wall_s
        except Exception:  # noqa: BLE001
            pass
        n = self.gate.reserve(self.label, prompt)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        (self.save_dir / f"{n:02d}-prompt.txt").write_text(prompt, encoding="utf-8", newline="\n")
        status, text, usage, detail = "incomplete", None, {}, ""
        try:
            async for ev in self.inner.query(prompt):
                ev = ev or {}
                t = ev.get("type")
                if t == "error":
                    status, detail = "engine_error", str(ev.get("content") or "")[:300]
                elif t == "tool_call":
                    status = "tool_call"
                elif t == "final":
                    for k in ("tokens_in", "tokens_out", "cost_usd"):
                        if ev.get(k) is not None:
                            usage[k] = ev[k]
                    if ev.get("is_error") or ev.get("dua_token"):
                        status, detail = "engine_result_error", str(ev.get("content") or "")[:300]
                    else:
                        text = ev.get("content") or ""
                        status = _output_status(text, self.max_chars) if status == "incomplete" else status
                yield ev
        finally:
            # Cả khi host thôi đọc (GeneratorExit) hay hết giờ (CancelledError): lượt đã có thể chạy, vẫn tính.
            out = {}
            if text is not None:
                (self.save_dir / f"{n:02d}-output.txt").write_text(text, encoding="utf-8", newline="\n")
                out = {"output_sha256": _sha(text), "output_chars": len(text)}
            self.gate.settle(n, status, detail=detail, usage=usage, **out)
            if status != "ok":
                self.gate.halt(f"call {n}: {status}")


def _output_status(text: str, max_chars: int) -> str:
    if not (text or "").strip():
        return "empty_output"
    if len(text) > max_chars:
        return "output_too_large"
    try:
        import aux_engine
        if aux_engine.final_loi_dang_nhap(text):
            return "engine_auth"
    except ImportError:
        pass
    return "ok"


# ───────────── Kịch bản dry: engine mang vai engine thật ─────────────

GOOD = ("# Ghi chú tổng hợp\n\n- Báo cáo quý: nộp cho phòng kế toán (anh Minh).\n"
        "- Máy lạnh ở kho: gọi thợ bảo trì (chị Lan).\n- Hợp đồng thuê kho: gia hạn trước cuối tháng (anh Tùng).\n")
HALF = "# Ghi chú tổng hợp\n\n- Báo cáo quý: nộp cho phòng kế toán.\n"


def _is_candidate(prompt: str) -> bool:
    import resonance as R
    return R.METHODS[FROZEN["candidate"]]["addendum"][:40] in prompt


def scripted(name):
    """Hàm (prompt, n) -> chữ, dict lỗi, hay ("sleep", giây) / ("exit", mã). n đếm từ 1 theo lời gọi qua cổng."""
    def win(prompt, n):
        return GOOD if _is_candidate(prompt) else HALF

    def same(prompt, n):
        return GOOD

    def regress(prompt, n):
        return HALF if _is_candidate(prompt) else GOOD

    def err_at(k, base=win):
        return lambda p, n: ({"type": "error", "content": "lỗi engine giả lập"} if n == k else base(p, n))

    return {
        "win": win, "no_improvement": same, "regression": regress,
        "unknown": lambda p, n: ("x" * 300_000) if n == 4 else win(p, n),
        "err_first": err_at(1), "err_last_trial": err_at(4), "err_followup": err_at(5),
        "timeout": lambda p, n: ("sleep", 5) if n == 1 else win(p, n),
        "crash": lambda p, n: ("exit", 17) if n == 2 else win(p, n),
        "storage_error": win, "gate_limit_mid": win, "token_low": win, "store_ceiling": win,
    }[name]


class DryEngine:
    def __init__(self, fn, counter: list):
        self.fn, self.counter, self.max_wall_s = fn, counter, None

    def is_available(self):
        return True

    async def query(self, prompt):
        self.counter[0] += 1
        out = self.fn(prompt, self.counter[0])
        if isinstance(out, tuple) and out[0] == "sleep":
            await asyncio.sleep(out[1])
            out = GOOD
        if isinstance(out, tuple) and out[0] == "exit":
            sys.stdout.flush()
            os._exit(out[1])
        if isinstance(out, dict):
            yield out
            return
        yield {"type": "final", "content": out, "tokens_in": 1, "tokens_out": 1}


class SeedEngine:
    """Ba lượt trước bế tắc: chữ cố định, không model."""

    def __init__(self):
        self.queries, self.max_wall_s = 0, None

    def is_available(self):
        return True

    async def query(self, prompt):
        self.queries += 1
        yield {"type": "final", "content": FROZEN["seed_output"], "tokens_in": 0, "tokens_out": 0}


# ───────────── Tiến trình con: một giai đoạn của một kịch bản ─────────────

def child(scenario: str, phase: int, base: Path, mode: str) -> dict:
    import main
    import resonance as R
    import resonance_store as RS

    state_file = base / "child-state.json"
    st = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    clock = [float(st.get("clock") or time.time())]

    def save_state(**kw):
        st.update(kw, clock=clock[0])
        state_file.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8", newline="\n")

    brain = main._brain_key("brain")
    P = RS.Principal("agent", "javis", brain)
    owner = RS.Principal("owner", "owner", brain)
    store = main._resonance_store()
    ss = main.get_store()
    calls_dir = base / "calls"

    def token_check():
        """Trước MỖI lượt thật: đăng nhập gói thuê bao gốc (claude auth status, không gọi model) và hạn token (chỉ đọc
        expiresAt). Không loại hết race làm mới token giữa chừng; chỉ giảm rủi ro."""
        if mode == "real":
            import claude_token_gate
            from claude_cli import tim_binary
            bg = Path(os.environ["JAVIS_STATE_DIR"]) / "resonance_cwd"
            bg.mkdir(parents=True, exist_ok=True)
            try:
                stt = json.loads(subprocess.run([tim_binary("claude"), "auth", "status", "--json"], cwd=str(bg),
                                                capture_output=True, text=True, timeout=60).stdout or "{}")
            except Exception as e:  # noqa: BLE001
                return False, f"không chạy được auth status: {type(e).__name__}"
            ok, why = G.check_auth_status(stt)
            if not ok:
                return False, why
            exp = claude_token_gate.han_token()
            left = round(exp - time.time()) if exp else None
            return (left is not None and left >= TOKEN_MIN_S), f"token còn {left} giây"
        if scenario == "token_low":
            return False, "còn 100 giây (giả lập)"
        return True, ""

    limit = 3 if scenario == "gate_limit_mid" else REAL_LIMIT
    gate = RealCallGate(base / "real-calls.json", limit, token_check=token_check,
                        closed="" if phase == 1 else "phase2_closed")
    counter = [0]
    inner_calls = []

    def gated_factory(system_prompt, tag):
        if mode == "real":
            inner, info = main._resonance_engine(system_prompt, tag)
            if inner is None:
                return None, info
        else:
            inner, info = DryEngine(scripted(scenario), counter), {"provider": "dry-as-real", "model": "dry",
                                                                    "text_only": True}
        inner_calls.append(info)
        return GatedEngine(inner, gate, calls_dir, f"{tag}", R.OUTPUT_MAX_CHARS), {**info, "pilot_gate": True}

    seed = SeedEngine()

    def seed_factory(system_prompt, tag):
        return seed, {"provider": "fake-seed", "model": "fake-seed", "text_only": True}

    wall = 1 if scenario == "timeout" else REAL_WALL_S

    def deps(factory):
        return R.GoalDeps(engine_factory=factory, budget=R.CallBudget(0), clock=lambda: clock[0], store=store,
                          principal=P, brain_root=brain, evidence=main._RESONANCE_EVIDENCE, notify=None,
                          max_wall_s=wall, wall_grace_s=0.5 if scenario == "timeout" else 30.0)

    def tick(factory):
        asyncio.run(R.tick(store, clock[0], lambda b: deps(factory), limit=5))
        asyncio.run(R.drain_outbox(store, main._resonance_notify, already=main._resonance_reported))

    def advance(gid):
        dues = [w["due_at"] for w in store.wakes(P, gid)]
        if not dues:
            return False
        clock[0] = max(clock[0], min(dues))
        save_state()
        return True

    out = {"scenario": scenario, "phase": phase, "mode": mode}
    if phase == 1:
        adir = Path(brain) / "agents"
        adir.mkdir(parents=True, exist_ok=True)
        (adir / f"{SLUG}.md").write_text(FROZEN["agent_md"], encoding="utf-8", newline="\n")
        agent = store.agent_set_enabled(owner, SLUG, True)
        sid = ss.create_session(brain=brain, engine="test", model="test", channel=f"agent:{SLUG}")
        mid = ss.append_message(sid, "user", FROZEN["user_1"])
        prop = {"understanding": FROZEN["understanding_1"], "criteria": FROZEN["criteria"],
                "relevant_quote": FROZEN["user_1"][:80], "stage": "delivery", "mode": "achieve",
                "horizon": {"kind": "review", "at_iso": "2027-02-20T09:00:00+07:00"}}
        d0 = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "không gọi"}), budget=R.CallBudget(0),
                        store=store)
        g = asyncio.run(R.form_goal(R.message_ref(sid, mid), {
            "principal": P, "brain_root": brain, "session_id": sid, "message_id": mid, "user_text": FROZEN["user_1"],
            "constraints": [], "budget_calls": FROZEN["budget_calls"], "proposal": prop,
            "agent_key": agent["agent_key"], "agent_version": agent["config_version"]}, d0))
        fr = dict(store.get_revision(P, g.id, 1), understanding=FROZEN["understanding_2"])
        mid2 = ss.append_message(sid, "user", FROZEN["user_2"])
        iid = store.add_intent(P, sid, mid2, FROZEN["user_2"], [], relation="replace")["id"]
        store.revise(P, g.id, 1, fr, "người dùng nói lại", intent_id=iid)
        save_state(goal_id=g.id, session_id=sid)
        # Gieo bế tắc bằng engine giả.
        for _ in range(30):
            ls = store.method_lessons(P, g.id)
            if ls and ls[-1]["status"] != "proposed" or not advance(g.id):
                break
            tick(seed_factory)
        g = store.get(P, g.id)
        ls = store.method_lessons(P, g.id)
        out["pre"] = {"seed_queries": seed.queries, "calls_used": g.calls_used, "status": g.status,
                      "lesson": [(x["status"], x["status_reason"]) for x in ls],
                      "pending": sorted(r["code"] for r in store.reasons(P, g.id)),
                      "full_cycle": list(R._full_cycle(g, 2)), "experiments": len(store.experiments(P, g.id)),
                      "real_calls": len(gate.calls())}
        save_state(pre=out["pre"])
        ready = (seed.queries == 3 and g.calls_used == 3 and ls and ls[-1]["status"] == "trial_pending"
                 and "method_trial" in out["pre"]["pending"] and out["pre"]["full_cycle"][0])
        out["pre"]["ready"] = bool(ready)
        if ready or scenario == "store_ceiling":
            if scenario == "storage_error":
                orig, fired = store.finish_experiment, []

                def failing(*a, **k):
                    if not fired:
                        fired.append(1)
                        raise OSError("lỗi lưu trữ giả lập khi chốt phép thử")
                    return orig(*a, **k)
                store.finish_experiment = failing
            for _ in range(40):
                if gate.halted() or len(gate.calls()) >= limit or _settled(store, P, g.id):
                    break
                if not advance(g.id):
                    break
                tick(gated_factory)
        if scenario == "win":
            # Lời gọi thứ sáu qua đúng đường bọc: phải bị từ chối, không tới engine, sổ giữ nguyên.
            before, n0 = len(gate.calls()), counter[0]
            eng, _ = gated_factory("probe", "probe")

            async def _probe():
                return [ev async for ev in eng.query("probe")]
            evs = asyncio.run(_probe())
            out["sixth"] = {"available": eng.is_available(), "events": evs, "ledger_before": before,
                            "ledger_after": len(gate.calls()), "inner_before": n0, "inner_after": counter[0]}
    else:
        g = store.get(P, st["goal_id"])
        out["before"] = snapshot(store, P, g.id, gate)
        for rnd in range(2):
            main._RESONANCE_STORE = None
            store = main._resonance_store()
            end = clock[0] + 2 * 86400
            for _ in range(200):
                dues = [w["due_at"] for w in store.wakes(P, g.id)]
                if not dues or min(dues) > end:
                    break
                clock[0] = max(clock[0], min(dues))
                tick(gated_factory)
            clock[0] = max(clock[0], end)
            save_state()
        out["refusals_phase2"] = len(gate.refusals)
    out["inner_calls"] = counter[0]
    out["after"] = snapshot(store, P, st["goal_id"], gate)
    return out


def _settled(store, P, gid) -> bool:
    ls = store.method_lessons(P, gid)
    holds = store.holds(P, gid)
    exps = store.experiments(P, gid)
    if not ls or ls[-1]["status"] in ("trial_pending", "trialing"):
        return False
    if any(e["status"] == "running" for e in exps) or any(h["status"] == "held" for h in holds):
        return False
    return True


def snapshot(store, P, gid, gate) -> dict:
    g = store.get(P, gid)
    acts = []
    for a in store.actions(P, gid):
        rc = a.get("receipt") or {}
        acts.append({"kind": a["kind"], "revision": a["revision"], "status": a["status"],
                     "provider": ((rc.get("engine") or {}).get("provider")), "error": rc.get("error_code", "")})
    exps = []
    for e in store.experiments(P, gid):
        pl = e.get("payload") or {}
        exps.append({"status": e["status"], "verdict": e["verdict"], "reason": e["reason"],
                     "applied": bool(e["applied"]), "calls_reserved": e["calls_reserved"],
                     "stop_detail": pl.get("stop_detail"), "cases_meta": pl.get("cases_meta"),
                     "results": [{k: r.get(k) for k in ("case_id", "split")} | {
                         "baseline": (r.get("baseline") or {}).get("verdict"),
                         "candidate": (r.get("candidate") or {}).get("verdict")} for r in pl.get("results") or []]})
    return {"goal": {"status": g.status, "calls_used": g.calls_used, "explore_used": g.explore_used,
                     "revision": g.revision, "method_ref": g.method_ref,
                     "run_state": (store.run_state(P, gid) or {}).get("block_reason")},
            "lessons": [(x["status"], x["status_reason"]) for x in store.method_lessons(P, gid)],
            "holds": [h["status"] for h in store.holds(P, gid)],
            "experiments": exps, "actions": acts,
            "pending": sorted(r["code"] for r in store.reasons(P, gid)),
            "real_calls": [{k: c.get(k) for k in ("n", "label", "status", "detail", "output_sha256", "output_chars")}
                           for c in gate.calls()],
            "gate_halted": gate.halted(), "branch": branch(exps, gate.halted(), store.holds(P, gid),
                                                           store.method_lessons(P, gid))}


def branch(exps, halted, holds, lessons) -> str:
    """Nhãn nhánh giữ nguyên nguyên nhân: lỗi kỹ thuật không bao giờ thành "cách làm thua"."""
    if halted:
        return f"technical_failed ({halted})"
    if not exps:
        ls = lessons[-1] if lessons else {}
        return f"no_trial ({ls.get('status')}/{ls.get('status_reason')})"
    e = exps[0]
    b = f"{e['verdict']}/{e['reason']}"
    if e["verdict"] == "eligible":
        b += f", followup hold {(holds[-1] if holds else {}).get('status')}"
    return b


# ───────────── Tiến trình cha ─────────────

def run_child(scenario: str, phase: int, base: Path, mode: str, env_extra=None) -> tuple:
    env = dict(G.clean_env(dict(os.environ)) if mode == "real" else os.environ)
    env.update({"JAVIS_STATE_DIR": str(base / "state"), "BRAINS_DIR": str(base / "brains"),
                "JAVIS_RESONANCE_TICK_PAUSED": "1", "PYTHONIOENCODING": "utf-8",
                "JAVIS_RESONANCE_CALL_CEILING": str(STORE_CEILING), "JAVIS_RESONANCE_A3_PILOT": mode})
    env.pop("JAVIS_PORT", None)
    env.update(env_extra or {})
    cp = subprocess.run([sys.executable, str(HERE), "--child", scenario, str(phase), str(base), mode],
                        cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=3600)
    res = None
    for ln in (cp.stdout or "").splitlines():
        if ln.startswith("CHILD_RESULT "):
            res = json.loads(ln[len("CHILD_RESULT "):])
    (base / f"phase{phase}.log").write_text((cp.stdout or "") + "\n--- stderr ---\n" + (cp.stderr or ""),
                                            encoding="utf-8", newline="\n")
    return cp.returncode, res


def prepare(base: Path, model: dict) -> None:
    (base / "state").mkdir(parents=True, exist_ok=True)
    (base / "brains" / "Brain Default" / "Inbox").mkdir(parents=True, exist_ok=True)
    (base / "state" / "settings.json").write_text(json.dumps({"model": model}, ensure_ascii=False), encoding="utf-8",
                                                  newline="\n")


_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info})"), flush=True)
    if not cond:
        _fails.append(name)


def frozen_hashes() -> dict:
    import resonance as R
    return {"user_1": _sha(FROZEN["user_1"]), "user_2": _sha(FROZEN["user_2"]), "criteria": _sha(FROZEN["criteria"]),
            "agent_md": _sha(FROZEN["agent_md"]), "seed_output": _sha(FROZEN["seed_output"]),
            "baseline_addendum": _sha(R.METHODS[FROZEN["baseline"]]["addendum"]),
            "candidate_addendum": _sha(R.METHODS[FROZEN["candidate"]]["addendum"]),
            "runner": _sha(HERE.read_bytes())}


# Kỳ vọng dry theo nhánh: (lượt thật, calls_used cuối, lượt giữ, bài học, phán quyết phép thử, cổng đóng)
EXPECT = {
    "win": (5, 8, "used", "active", ("eligible", "improved"), False),
    "no_improvement": (4, 7, "released", "rejected", ("rejected", "no_improvement"), False),
    "regression": (4, 7, "released", "rejected", ("rejected", "regression"), False),
    "unknown": (4, 7, "released", "unknown", ("inconclusive", "unknown"), True),
    "err_first": (1, 4, "released", "unknown", ("inconclusive", "unknown"), True),
    "err_last_trial": (4, 7, "released", "unknown", ("inconclusive", "unknown"), True),
    "err_followup": (5, 8, "used", "active", ("eligible", "improved"), True),
    "timeout": (1, 4, "released", "unknown", ("inconclusive", "unknown"), True),
    "token_low": (0, 3, "released", "unknown", ("inconclusive", "unknown"), True),
    "gate_limit_mid": (3, 6, "released", "unknown", ("inconclusive", "unknown"), False),
    "crash": (2, 5, "released", "unknown", ("inconclusive", "interrupted"), True),
    "storage_error": (4, 7, "released", "unknown", ("inconclusive", "interrupted"), False),
}


def judge(scenario, p1, p2) -> dict:
    a = (p2 or {}).get("after") or {}
    exp = EXPECT.get(scenario)
    got = {"real": len(a.get("real_calls") or []), "calls_used": (a.get("goal") or {}).get("calls_used"),
           "hold": (a.get("holds") or [None])[-1], "lesson": ((a.get("lessons") or [[None]])[-1])[0],
           "trial": tuple(((a.get("experiments") or [{}])[0].get(k) for k in ("verdict", "reason"))),
           "halted": bool(a.get("gate_halted"))}
    return {"expect": exp, "got": got}


def main_dry() -> None:
    root = Path(tempfile.mkdtemp(prefix="rsa3p-dry-", dir=os.environ.get("TEMP") or None)).resolve()
    print(f"Dry, thư mục {root}", flush=True)
    t0 = time.time()
    report = {"mode": "dry", "frozen": frozen_hashes(), "scenarios": {}}
    dry_model = {"auxiliary": {"provider": "dry-as-real", "model": "dry"}}
    only = [s for s in os.environ.get("JAVIS_RESONANCE_A3_ONLY", "").split(",") if s]
    for sc in [s for s in list(EXPECT) + ["store_ceiling"] if not only or s in only]:
        base = root / sc
        prepare(base, dry_model)
        extra = {"JAVIS_RESONANCE_CALL_CEILING": "7"} if sc == "store_ceiling" else None
        rc1, p1 = run_child(sc, 1, base, "dry", extra)
        rc2, p2 = run_child(sc, 2, base, "dry", extra)
        report["scenarios"][sc] = {"rc": [rc1, rc2], "phase1": p1, "phase2": p2}
        pre = (p1 or {}).get("pre") or {}
        if sc == "crash":
            check("crash: tiến trình chết đúng giữa lời gọi thật thứ 2 (mã 17)", rc1 == 17 and p1 is None, rc1)
        else:
            check(f"{sc}: tiền điều kiện trước lượt thật (3 lượt giả, calls 3, trial_pending, method_trial, đủ "
                  f"ngân sách trọn vòng, 0 lượt thật)",
                  rc1 == 0 and pre.get("ready") and pre.get("real_calls") == 0, pre)
        if sc == "store_ceiling":
            a = (p2 or {}).get("after") or {}
            check("store_ceiling: trần kho 7 (thiếu 1 so với 3 + 4 + 1) thì không mở phép thử, 0 lượt thật",
                  rc2 == 0 and not a.get("experiments") and not a.get("real_calls")
                  and (a.get("lessons") or [[None]])[-1][0] == "skipped", a.get("lessons"))
            continue
        j = judge(sc, p1, p2)
        n, used, hold, lesson, trial, halted = j["expect"]
        got = j["got"]
        check(f"{sc}: {n} lượt thật, calls_used {used}, lượt giữ {hold}, bài học {lesson}, phép thử {trial[0]}/"
              f"{trial[1]}, cổng {'đóng' if halted else 'mở'}",
              rc2 == 0 and got == {"real": n, "calls_used": used, "hold": hold, "lesson": lesson, "trial": trial,
                                   "halted": halted}, got)
        b, a = (p2 or {}).get("before") or {}, (p2 or {}).get("after") or {}
        same = {k: a.get(k) for k in ("goal", "lessons", "holds", "real_calls")} == \
            {k: b.get(k) for k in ("goal", "lessons", "holds", "real_calls")}
        if sc in ("crash", "storage_error"):
            check(f"{sc}: tiến trình mới đối soát xong, không phép thử nào còn running, không lượt giữ nào còn held",
                  all(e["status"] != "running" for e in a.get("experiments") or []) and "held" not in a.get("holds", []),
                  a.get("experiments"))
        else:
            check(f"{sc}: khởi động lại và đối soát hai lượt không đổi trạng thái", same,
                  {"before": b.get("goal"), "after": a.get("goal")})
        check(f"{sc}: giai đoạn 2 không gọi engine nào (cổng đóng hẳn)", (p2 or {}).get("inner_calls") == 0
              and len(a.get("real_calls") or []) == len(b.get("real_calls") or []), (p2 or {}).get("inner_calls"))
        seeds = [x for x in a.get("actions") or [] if x.get("provider") == "fake-seed"]
        check(f"{sc}: ba lượt giả ghi rõ provider fake-seed", len(seeds) == 3, len(seeds))
        if sc == "win":
            s6 = (p1 or {}).get("sixth") or {}
            check("win: lời gọi thứ sáu bị cổng từ chối trước engine, sổ giữ 5",
                  s6.get("available") is False and s6.get("ledger_before") == s6.get("ledger_after") == 5
                  and s6.get("inner_before") == s6.get("inner_after"), s6)
    report["seconds"] = round(time.time() - t0)
    (root / "dry-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str),
                                          encoding="utf-8", newline="\n")
    out = os.environ.get("JAVIS_RESONANCE_A3_OUT", "")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        shutil.copy(root / "dry-report.json", Path(out) / "dry-report.json")
    print(f"\nDry xong trong {report['seconds']} giây, 0 lượt model thật. Báo cáo: {root / 'dry-report.json'}")


def resolve_engines(state: Path, env0: dict) -> dict:
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


APPROVED = {"aux": {"provider": "anthropic-cli", "model": "sonnet"}}


def auth_gate(base: Path, env0: dict) -> dict:
    """Cổng của pilot A1 (không gọi model): engine việc nền khớp cấu hình duyệt, đúng binary claude, đăng nhập gói thuê
    bao gốc ở thư mục làm việc của việc nền, settings không có apiKeyHelper hay env chọn khoá, không có nguồn quản trị."""
    state, brain = base / "state", base / "brains" / "Brain Default"
    bg = state / "resonance_cwd"
    bg.mkdir(parents=True, exist_ok=True)
    out = {"ok": False, "why": "", "approved": APPROVED}
    out["engines"] = eng = resolve_engines(state, env0)
    ok, why = G.check_engines(eng, APPROVED)
    if not ok:
        out["why"] = "engine sẽ chạy khác cấu hình đã duyệt: " + why
        return out
    cp = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, 'server'); "
                         "from claude_cli import tim_binary; print(tim_binary('claude') or '')"],
                        cwd=str(ROOT), env=env0, capture_output=True, text=True, timeout=60)
    cli = (cp.stdout or "").strip().splitlines()[-1] if (cp.stdout or "").strip() else ""
    if not cli:
        out["why"] = "không tìm thấy binary claude"
        return out
    ver = subprocess.run([cli, "--version"], cwd=str(bg), env=env0, capture_output=True, text=True, timeout=60)
    out["cli_version"] = (ver.stdout or "").strip()[:60]
    stt = json.loads(subprocess.run([cli, "auth", "status", "--json"], cwd=str(bg), env=env0, capture_output=True,
                                    text=True, timeout=60).stdout or "{}")
    out["auth"] = G.auth_metadata(stt)
    ok, why = G.check_auth_status(stt)
    if not ok:
        out["why"] = why
        return out
    cfg = Path(stt.get("configDirectory") or (Path.home() / ".claude"))
    paths = G.settings_paths(cfg, brain) + G.settings_paths(cfg, bg)[2:4]
    out["settings"] = G.scan_settings(paths)
    out["managed_sources"] = G.managed_sources(cfg)
    out["not_assessed"] = G.ancillary_sources(paths)
    if out["settings"]["risky"]:
        out["why"] = "nguồn settings có apiKeyHelper hay env chọn nhà cung cấp/khoá"
        return out
    if out["managed_sources"]:
        out["why"] = "có nguồn settings do quản trị đặt"
        return out
    out["ok"] = True
    return out


def main_preflight() -> None:
    """Chỉ cổng xác thực trên settings thật (bốn trường chọn engine), không dựng mục tiêu, không gọi model."""
    src = os.environ.get("JAVIS_RESONANCE_PILOT_SETTINGS", "")
    if not src or not Path(src).is_file():
        print("FAIL preflight: cần JAVIS_RESONANCE_PILOT_SETTINGS")
        sys.exit(1)
    m = json.loads(Path(src).read_text(encoding="utf-8")).get("model") or {}
    model = {k: m[k] for k in ("auxiliary", "main", "engine", "claude_model") if k in m}
    base = Path(tempfile.mkdtemp(prefix="rsa3p-pre-", dir=os.environ.get("TEMP") or None)).resolve()
    prepare(base, model)
    gate = auth_gate(base, G.clean_env(dict(os.environ)))
    print("PREFLIGHT " + json.dumps({"model": model, **gate}, ensure_ascii=False, default=str))
    check("cổng xác thực trên settings thật (không gọi model)", gate["ok"], gate.get("why"))


def main_real() -> None:
    src = os.environ.get("JAVIS_RESONANCE_PILOT_SETTINGS", "")
    outd = os.environ.get("JAVIS_RESONANCE_A3_OUT", "")
    if not src or not Path(src).is_file() or not outd:
        print("FAIL pilot: cần JAVIS_RESONANCE_PILOT_SETTINGS (settings.json thật) và JAVIS_RESONANCE_A3_OUT")
        sys.exit(1)
    m = json.loads(Path(src).read_text(encoding="utf-8")).get("model") or {}
    model = {k: m[k] for k in ("auxiliary", "main", "engine", "claude_model") if k in m}
    base = Path(tempfile.mkdtemp(prefix="rsa3p-real-", dir=os.environ.get("TEMP") or None)).resolve()
    prepare(base, model)
    env0 = G.clean_env(dict(os.environ))
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "server", "system", "tests"],
                           capture_output=True, text=True).stdout.strip()
    rep = {"mode": "real", "commit": commit, "tree_dirty": bool(dirty), "frozen": frozen_hashes(), "base": str(base),
           "limit_real_calls": REAL_LIMIT, "store_ceiling": STORE_CEILING}
    gate = auth_gate(base, env0)
    rep["auth_gate"] = gate
    check("cây mã server/system/tests sạch ở commit chạy", not dirty, dirty[:200])
    check("cổng xác thực (không gọi model)", gate["ok"], gate.get("why"))
    p1 = p2 = None
    if not _fails:
        rc1, p1 = run_child("real", 1, base, "real")
        rc2, p2 = run_child("real", 2, base, "real")
        rep.update(rc=[rc1, rc2], phase1=p1, phase2=p2)
        a = (p2 or {}).get("after") or {}
        n = len(a.get("real_calls") or [])
        check(f"lượt thật {n} <= {REAL_LIMIT}", n <= REAL_LIMIT, n)
        check("giai đoạn 2 không gọi engine", (p2 or {}).get("inner_calls") == 0)
        check("ba lượt giả ghi rõ fake-seed",
              len([x for x in a.get("actions") or [] if x.get("provider") == "fake-seed"]) == 3)
        check("không phép thử nào còn running, không lượt giữ nào còn held",
              all(e["status"] != "running" for e in a.get("experiments") or []) and "held" not in a.get("holds", []))
    rep["branch"] = ((p2 or {}).get("after") or {}).get("branch")
    rep["conclusion"] = "technical_failed" if _fails else "pending_content_review"
    Path(outd).mkdir(parents=True, exist_ok=True)
    if (base / "calls").exists():
        shutil.copytree(base / "calls", Path(outd) / "calls", dirs_exist_ok=True)
    for f in ("real-calls.json", "phase1.log", "phase2.log"):
        if (base / f).exists():
            shutil.copy(base / f, Path(outd) / f)
    (Path(outd) / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str),
                                            encoding="utf-8", newline="\n")
    print(f"\nKết luận: {rep['conclusion']}. Báo cáo: {Path(outd) / 'report.json'}")


if CHILD:
    i = sys.argv.index("--child")
    sc, ph, bs, md = sys.argv[i + 1], int(sys.argv[i + 2]), Path(sys.argv[i + 3]), sys.argv[i + 4]
    res = child(sc, ph, bs, md)
    print("CHILD_RESULT " + json.dumps(res, ensure_ascii=False, default=str), flush=True)
    sys.exit(0)

if MODE == "dry":
    main_dry()
elif MODE == "preflight":
    main_preflight()
else:
    main_real()
if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
