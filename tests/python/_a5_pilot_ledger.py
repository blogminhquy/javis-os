"""Hàm dùng chung của bộ chạy pilot A5: sổ lượt theo vai, đối chiếu kết cục với host, kết luận, bảo toàn bằng chứng, kiểm
nguồn trước khi chạy. Dùng ở `_a5_pilot_server.py`, `test_resonance_a5_pilot.py`, `test_resonance_a5_pilot_gate.py`.

Sổ là một file JSON {"run_id", "caps": {"maker", "reviewer", "total"}, "calls": [...], "events": [...]}, ghi bằng fsync
rồi os.replace. Mỗi lượt engine của việc nền (một lần dựng engine cho một lượt làm hay review) được GIỮ CHỖ trong sổ
TRƯỚC khi dựng engine. Kết cục của lượt theo ĐÚNG luật lỗi của host (`GoalDeps._ask`): khung `error`, `final` có
`is_error` hay `dua_token`, gọi công cụ trong lượt chỉ chữ, đầu ra rỗng hay quá dài, lời báo lỗi đăng nhập, ngoại lệ,
huỷ, thiếu khung kết thúc, cộng với kết luận cuối của chính `_ask`. `ok` chỉ là TẠM: lỗi đến sau hạ nó xuống, không bao giờ
nâng lỗi thành `ok`. Mọi kết cục khác `ok` và mọi lượt giữ chỗ chưa có kết cục đều ĐÓNG sổ (vẫn tính lượt). Sổ đọc lỗi hay
sai cấu trúc thì không cấp lượt và KHÔNG ghi đè. Lần thử bị chặn ghi một sự kiện `refused`, không phải một lượt.
"""
import asyncio
import contextvars
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

ROLES = ("maker", "reviewer")
_STATUS_RE = re.compile(r"^[a-z][a-z_]{0,39}$")
# Lượt đang chạy trong tác vụ hiện tại (hàm dựng đặt, `wrap_ask` đọc): đối chiếu kết luận của host với đúng dòng sổ.
CURRENT_CALL = contextvars.ContextVar("a5_pilot_call", default=0)


class RoleLedger:
    def __init__(self, path, phase_caps: dict):
        self.path = Path(path)
        self.phase_caps = dict(phase_caps or {})

    # ───── đọc ghi ─────
    def write(self, st: dict) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(st, ensure_ascii=False, indent=1))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def load(self) -> tuple:
        try:
            st = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            return None, f"ledger_unreadable: {type(e).__name__}"
        calls = st.get("calls") if isinstance(st, dict) else None
        caps = st.get("caps") if isinstance(st, dict) else None
        if not isinstance(calls, list) or not isinstance(caps, dict) or not isinstance(st.get("events"), list) \
                or not all(type(caps.get(k)) is int and caps[k] >= 0 for k in ("maker", "reviewer", "total")):
            return None, "ledger_bad_shape"
        for i, c in enumerate(calls, 1):
            if not isinstance(c, dict) or c.get("n") != i or c.get("role") not in ROLES \
                    or not isinstance(c.get("status"), str) or not _STATUS_RE.match(c["status"]):
                return None, f"ledger_bad_call_{i}"
        return st, ""

    def event(self, st: dict, kind: str, **kw) -> None:
        st["events"].append({"kind": kind, "at": time.time(), "pid": os.getpid(), **kw})

    # ───── giữ chỗ và chốt ─────
    def reserve(self, role: str) -> tuple:
        """(số thứ tự, "") khi được gọi; (0, lý do) khi bị chặn. Ghi xuống đĩa TRƯỚC khi trả."""
        st, err = self.load()
        if err:
            return 0, err
        why = ""
        if role not in ROLES:
            why = "role_other"
        elif any(c["status"] == "reserved" for c in st["calls"]):
            why = "reserved_without_outcome"
        elif any(c["status"] != "ok" for c in st["calls"]):
            why = "halted_after_" + next(c["status"] for c in st["calls"] if c["status"] != "ok")
        else:
            used = sum(1 for c in st["calls"] if c["role"] == role)
            if used >= int(self.phase_caps.get(role, 0)) or used >= int(st["caps"].get(role, 0)):
                why = f"cap_{role}"
            elif len(st["calls"]) >= int(st["caps"]["total"]):
                why = "cap_total"
        if why:
            self.event(st, "refused", role=role, why=why, phase_caps=self.phase_caps)
            self.write(st)
            return 0, why
        n = len(st["calls"]) + 1
        st["calls"].append({"n": n, "role": role, "status": "reserved", "at": time.time(), "pid": os.getpid()})
        self.write(st)
        return n, ""

    def settle(self, n: int, status: str, **kw) -> None:
        """Chốt kết cục của lượt `n` nếu nó còn `reserved` (chốt lần hai không đổi gì)."""
        st, err = self.load()
        if err or not _STATUS_RE.match(str(status)) or status == "reserved":
            return
        changed = False
        for c in st["calls"]:
            if c["n"] == n and c["status"] == "reserved":
                c.update(status=status, settled_at=time.time(), **kw)
                changed = True
        if changed:
            self.write(st)

    def mark_bad(self, n: int, status: str, **kw) -> None:
        """Lỗi đã thấy THẮNG thành công tạm: `reserved` hay `ok` thành `status` (lỗi đầu tiên được giữ, `ok` trước đó ghi
        lại ở `downgraded_from`). Không bao giờ nâng một lỗi thành `ok`, không đổi lỗi này sang lỗi khác."""
        if status in ("ok", "reserved") or not _STATUS_RE.match(str(status)):
            return
        st, err = self.load()
        if err:
            return
        changed = False
        for c in st["calls"]:
            if c["n"] == n and c["status"] in ("reserved", "ok"):
                if c["status"] == "ok":
                    kw = {**kw, "downgraded_from": "ok"}
                c.update(status=status, settled_at=time.time(), **kw)
                changed = True
        if changed:
            self.write(st)

    def note(self, n: int, **kw) -> None:
        st, err = self.load()
        if err:
            return
        for c in st["calls"]:
            if c["n"] == n:
                c.update(**kw)
        self.write(st)

    def tripwire(self, role: str) -> None:
        st, err = self.load()
        if not err:
            self.event(st, "tripwire", role=role)
            self.write(st)


def host_text_verdict(text: str) -> str:
    """Luật của `_ask` cho chữ của khung `final` hợp lệ: rỗng, quá dài, lời báo lỗi đăng nhập là lỗi. Đọc hằng và hàm
    của host khi import được (launcher, test), không thì chỉ kiểm rỗng."""
    t = str(text or "")
    if not t.strip():
        return "empty_output"
    try:
        import resonance as _R
        if len(t) > int(_R.OUTPUT_MAX_CHARS):
            return "output_too_large"
    except Exception:  # noqa: BLE001
        pass
    try:
        import aux_engine as _A
        if _A.final_loi_dang_nhap(t):
            return "engine_auth"
    except Exception:  # noqa: BLE001
        pass
    return "ok"


class Counted:
    """Bọc engine của MỘT lượt, áp đúng luật lỗi của host trên từng khung:
    - `tool_call` (trước hay sau `final`): `tool_call_in_text_only`;
    - `error`: `engine_error`;
    - `final` có `dua_token`: `engine_session_race`; có `is_error`: `engine_result_error`; chữ rỗng, quá dài, báo lỗi đăng
      nhập: theo `host_text_verdict`; còn lại `ok` TẠM, chốt ngay (host có thể ngừng đọc sau khung đó);
    - lỗi, công cụ, ngoại lệ, huỷ đến SAU `ok` tạm: hạ xuống lỗi (mark_bad);
    - hết luồng mà không có kết cục: `no_final`.
    Mọi kết cục đều tính lượt; kết cục khác `ok` đóng sổ."""

    def __init__(self, inner, ledger: RoleLedger, n: int, text_verdict=host_text_verdict):
        object.__setattr__(self, "inner", inner)
        object.__setattr__(self, "ledger", ledger)
        object.__setattr__(self, "n", n)
        object.__setattr__(self, "text_verdict", text_verdict)

    def __getattr__(self, k):
        return getattr(self.inner, k)

    def __setattr__(self, k, v):
        # Host đặt `max_wall_s` lên engine: chuyển xuống engine thật để trần thời gian của nó vẫn áp dụng.
        setattr(self.inner, k, v)

    async def query(self, prompt):
        # `at_yield`: generator đang dừng ở điểm trả khung cho host. Huỷ hay đóng đến ĐÚNG ở đó nghĩa là host đã ngừng đọc
        # (hay vòng lặp đóng generator bị bỏ dở): kết cục đã chốt giữ nguyên. Huỷ đến trong lúc CHỜ engine (host còn đọc:
        # hết giờ, huỷ lượt) là lỗi, kể cả sau `final`.
        state = {"seen": False, "tools": 0, "ok": False, "at_yield": False}

        def bad(status, **kw):
            self.ledger.mark_bad(self.n, status, **kw)
            state["seen"] = True

        try:
            async for ev in self.inner.query(prompt):
                t = ev.get("type") if isinstance(ev, dict) else None
                if t == "tool_call":
                    state["tools"] += 1
                    bad("tool_call_in_text_only")
                elif t == "error":
                    bad("engine_error", error=str(ev.get("content") or "")[:300])
                elif t == "final":
                    if ev.get("dua_token"):
                        bad("engine_session_race")
                    elif ev.get("is_error"):
                        bad("engine_result_error", subtype=str(ev.get("subtype") or "")[:60])
                    elif state["tools"]:
                        bad("tool_call_in_text_only")
                    else:
                        v = self.text_verdict(ev.get("content") or "")
                        if v == "ok":
                            self.ledger.settle(self.n, "ok", **{k: ev.get(k) for k in ("tokens_in", "tokens_out")
                                                                if ev.get(k) is not None})
                            state["seen"] = state["ok"] = True
                        else:
                            bad(v)
                state["at_yield"] = True
                yield ev
                state["at_yield"] = False
        except (asyncio.CancelledError, GeneratorExit) as e:
            if state["at_yield"] and state["seen"]:
                # Host ngừng đọc sau khi kết cục đã chốt: giữ nguyên (ok hay lỗi).
                raise
            if state["at_yield"]:
                bad("no_final")
            else:
                bad("cancelled" if isinstance(e, asyncio.CancelledError) else "no_final")
            raise
        except Exception as e:  # noqa: BLE001
            bad("exception", error=f"{type(e).__name__}: {str(e)[:200]}")
            raise
        if not state["seen"]:
            bad("no_final")


def wrap_factory(real_factory, ledger: RoleLedger, role_of, text_verdict=host_text_verdict):
    """Hàm dựng engine bọc sổ: giữ chỗ TRƯỚC khi dựng; bị chặn thì trả (None, lý do) và KHÔNG gọi `real_factory`. Ghi số
    lượt vào CURRENT_CALL để `wrap_ask` đối chiếu kết luận cuối của host."""
    def factory(system_prompt, tag="resonance"):
        role = role_of(system_prompt)
        n, why = ledger.reserve(role)
        if not n:
            return None, {"blocked": f"pilot_ledger:{why}"}
        CURRENT_CALL.set(n)
        try:
            eng, info = real_factory(system_prompt, tag)
        except Exception as e:  # noqa: BLE001
            ledger.mark_bad(n, "not_built", error=f"{type(e).__name__}: {str(e)[:200]}")
            raise
        if eng is None:
            ledger.mark_bad(n, "not_built", info={k: str(v)[:200] for k, v in (info or {}).items()})
            return None, info
        ledger.note(n, engine={k: (info or {}).get(k) for k in ("provider", "model") if (info or {}).get(k)})
        return Counted(eng, ledger, n, text_verdict), info
    return factory


def wrap_ask(orig_ask, ledger: RoleLedger):
    """Lớp thứ hai: đối chiếu kết luận CUỐI của `GoalDeps._ask` (host) với dòng sổ của lượt vừa dựng. Host báo lỗi sau khi
    đã gọi engine (`called`) thì dòng sổ thành `host_<mã>` dù khung có vẻ thành công; ngoại lệ hay huỷ thoát khỏi `_ask`
    cũng hạ dòng sổ. Không có lượt (bị chặn trước khi dựng) thì không làm gì."""
    async def ask(self, system_prompt, prompt):
        tok = CURRENT_CALL.set(0)
        try:
            try:
                turn = await orig_ask(self, system_prompt, prompt)
            except asyncio.CancelledError:
                n = CURRENT_CALL.get()
                if n:
                    ledger.mark_bad(n, "cancelled")
                raise
            except Exception as e:  # noqa: BLE001
                n = CURRENT_CALL.get()
                if n:
                    ledger.mark_bad(n, "exception", error=f"{type(e).__name__}: {str(e)[:200]}")
                raise
            n = CURRENT_CALL.get()
            code = str(getattr(turn, "error_code", "") or "")
            if n and getattr(turn, "called", False) and code:
                ledger.mark_bad(n, "host_" + re.sub(r"[^a-z_]", "_", code.lower())[:34], host_error=code)
            return turn
        finally:
            CURRENT_CALL.reset(tok)
    return ask


# ───── hàm thuần của bộ chạy ─────

def ledger_counts(st: dict) -> dict:
    """Số lượt đã giữ chỗ theo vai (mọi kết cục đều tính), kết cục khác ok, lần bị chặn, sự kiện bẫy."""
    calls = st["calls"]
    return {"maker": sum(1 for c in calls if c["role"] == "maker"),
            "reviewer": sum(1 for c in calls if c["role"] == "reviewer"),
            "total": len(calls), "not_ok": [c["status"] for c in calls if c["status"] != "ok"],
            "not_ok_roles": [c["role"] for c in calls if c["status"] != "ok"],
            "refused": [e.get("why") for e in st["events"] if e.get("kind") == "refused"],
            "tripwire": sum(1 for e in st["events"] if e.get("kind") == "tripwire")}


def classify(status: str, verdicts: list, work: list, refused: list, block_reason: str = "",
             reviewer_failed: bool = False) -> str:
    """Nhánh đã xảy ra, đọc từ kho và sổ (không ép). `verdicts`: kết luận hợp lệ theo thứ tự; `work`: trạng thái các lượt
    làm; `refused`: lý do các lần sổ chặn; `block_reason`: lý do chặn hiện tại; `reviewer_failed`: có lượt review mà sổ
    ghi kết cục khác `ok` (lỗi engine của vai review, không phải review không đọc được).

    Lượt sửa thứ hai có thể bị chặn ở trần kho của pilot (chặn lúc giữ chỗ, `blocked/budget`) hay ở sổ pilot (`refused
    cap_*`, host hoàn lượt, `blocked/engine_blocked`): cùng một nhánh."""
    if any(w != "succeeded" for w in work[:1]):
        return "maker_error"
    if reviewer_failed:
        return "reviewer_error"
    if status == "succeeded" and verdicts == ["pass"]:
        return "pass_first"
    if status == "succeeded" and verdicts == ["needs_changes", "pass"]:
        return "one_fix_then_pass"
    if verdicts[:2] == ["needs_changes", "needs_changes"] and (
            any(str(r).startswith("cap_") for r in refused) or block_reason in ("budget", "engine_blocked")):
        return "pilot_cap_after_two_reviews"
    if verdicts and verdicts[-1] == "unknown":
        return "review_unknown"
    if not verdicts and work and work[0] == "succeeded":
        return "maker_not_met"
    if not verdicts:
        return "no_review"
    return "other"


# Nhánh có thể dẫn tới duyệt nội dung (mục tiêu chốt đạt) và nhánh nghiệp vụ chưa đạt nhưng chạy đúng; kèm số lượt
# (làm, review) đúng của nhánh và trạng thái mục tiêu phải thấy.
BRANCH_RULES = {
    "pass_first": {"calls": (1, 1), "goal": "succeeded", "result": "pending_content_review"},
    "one_fix_then_pass": {"calls": (2, 2), "goal": "succeeded", "result": "pending_content_review"},
    "pilot_cap_after_two_reviews": {"calls": (2, 2), "goal": "active", "result": "business_incomplete"},
    "review_unknown": {"calls": (1, 1), "goal": "active", "result": "business_incomplete"},
    "maker_not_met": {"calls": (1, 0), "goal": "active", "result": "business_incomplete"},
}
EXIT_CODES = {"pending_content_review": 0, "business_incomplete": 2}


def decide_acceptance(rep: dict, fails: list, mode: str) -> tuple:
    """Kết luận của MỘT lần chạy, chỉ từ bằng chứng cuối (cùng luật cho real và dry). Trả (kết luận, lý do).

    - `stopped`: dừng ở một cổng TRƯỚC giai đoạn việc nền (không server nào có thể gọi model).
    - `technical_failed`: bất kỳ điều nào sau: kiểm hỏng; dừng sau khi giai đoạn việc nền đã bắt đầu; giai đoạn việc nền
      không kết thúc bình thường (hết giờ, sổ hỏng, bẫy); sổ ở lần đọc CUỐI không xác minh được; có lượt kết cục khác
      `ok`; sổ lượt engine của server không xác minh được; dựng lại chưa kiểm hay có lượt mới; nhánh không thuộc
      BRANCH_RULES; số lượt (sổ và sổ vai của kho) khác số của nhánh; trạng thái mục tiêu khác của nhánh; thiếu đầu ra đã
      lưu của mỗi lượt làm, mỗi lượt review, hay file đích khi mục tiêu chốt; ảnh chụp review không băm lại đúng; bảo toàn
      bằng chứng lỗi.
    - `pending_content_review`: kỹ thuật đạt trọn và mục tiêu chốt đạt (pass_first, one_fix_then_pass): chờ người đọc nội
      dung. Không có "đạt" tự động.
    - `business_incomplete`: kỹ thuật đạt trọn, nhánh nghiệp vụ chưa đạt nhưng đã định nghĩa (chạm trần pilot, review không
      đọc được, bản làm chưa đạt kiểm khách quan). Giữ nguyên `branch`.
    Thiếu trường nào thì coi như không đạt (đóng khi lỗi), không bao giờ suy ra đạt."""
    why = []
    started = bool(rep.get("phase_B_started"))
    if rep.get("stopped") and not started:
        return "stopped", [str(rep["stopped"])]
    if fails:
        why.append(f"{len(fails)} kiểm hỏng")
    if rep.get("stopped"):
        why.append("dừng sau khi việc nền đã bắt đầu: " + str(rep["stopped"]))
    stop = (rep.get("phase_B") or {}).get("stop")
    if stop not in ("goal_succeeded", "quiet", "goal_paused"):
        why.append(f"giai đoạn việc nền dừng bất thường ({stop})")
    if rep.get("ledger_status") != "verified":
        why.append(f"sổ ở lần đọc cuối không xác minh được ({rep.get('ledger_status')})")
    lc = rep.get("ledger_final_counts") or {}
    if not lc:
        why.append("không có số lượt cuối của sổ")
    if lc.get("not_ok"):
        why.append(f"lượt kết cục khác ok: {lc['not_ok']}")
    if lc.get("tripwire"):
        why.append("chạm bẫy engine")
    if rep.get("engine_turns_status") != "verified":
        why.append(f"sổ lượt engine của server không xác minh được ({rep.get('engine_turns_status')})")
    rs = rep.get("restart") or {}
    if rs.get("ok") is not True:
        why.append("dựng lại chưa kiểm hay có lượt mới")
    if (rep.get("preserve") or {}).get("ok") is not True:
        why.append("bảo toàn bằng chứng lỗi")
    branch = rep.get("branch")
    rule = BRANCH_RULES.get(branch)
    if rule is None:
        why.append(f"nhánh {branch} không phải kết cục hợp lệ")
    else:
        mk, rv = rule["calls"]
        if (lc.get("maker"), lc.get("reviewer")) != (mk, rv):
            why.append(f"sổ ({lc.get('maker')}, {lc.get('reviewer')}) khác số của nhánh ({mk}, {rv})")
        tc = (rep.get("store_B") or {}).get("team_calls") or {}
        if ((tc.get("maker") or {}).get("used"), (tc.get("reviewer") or {}).get("used")) != (mk, rv):
            why.append("sổ vai của kho khác số của nhánh")
        if ((rep.get("store_B") or {}).get("goal") or {}).get("status") != rule["goal"]:
            why.append(f"trạng thái mục tiêu khác của nhánh ({rule['goal']})")
        saved = rep.get("saved") or []
        if sum(1 for s in saved if s.get("role") == "maker" and s.get("ok") is True) != mk:
            why.append("thiếu đầu ra đã lưu của lượt làm")
        if sum(1 for s in saved if s.get("role") == "reviewer" and s.get("ok") is True) != rv:
            why.append("thiếu đầu ra đã lưu của lượt review")
        if any(s.get("ok") is not True for s in saved):
            why.append("có bằng chứng lưu lỗi")
        if rule["goal"] == "succeeded" and not any(s.get("role") == "deliverable" and s.get("ok") is True
                                                   for s in saved):
            why.append("thiếu file đích đã lưu")
        snap = rep.get("snapshot_hash_ok")
        if rv and not (isinstance(snap, list) and len(snap) == rv and all(x is True for x in snap)):
            why.append("ảnh chụp review chưa băm lại đúng cho mọi lượt review")
    if why:
        return "technical_failed", why
    return rule["result"], []


# ───── bảo toàn bằng chứng ─────

_SECRET_RE = re.compile(r"(?i)(sk-ant-[A-Za-z0-9_\-]+|bearer\s+[A-Za-z0-9._\-]+|"
                        r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|oauth[_-]?token)"
                        r"[\"']?\s*[:=]\s*[\"']?[^\s\"',}]+)")


def redact(text: str) -> str:
    """Che khoá và token trong log trước khi chép ra hồ sơ."""
    return _SECRET_RE.sub("<redacted>", str(text or ""))


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _xp(p) -> str:
    """Đường dẫn tuyệt đối; trên Windows dùng dạng `\\\\?\\` để không vướng giới hạn 260 ký tự khi hồ sơ nằm sâu."""
    s = os.path.abspath(str(p))
    if os.name == "nt" and not s.startswith("\\\\?\\"):
        return "\\\\?\\" + s
    return s


def preserve_sandbox(base: Path, dest_root: Path, required=(), fault=None) -> dict:
    """Chép bằng chứng cần hậu kiểm từ sandbox `base` sang một thư mục MỚI trong `dest_root` (không ghi đè gì có sẵn),
    SAU khi mọi server đã dừng. Danh sách cho phép, không chép khoá hay kho bí mật:
    - `state/resonance.sqlite3`, `state/conversations.db`: bản sao bằng SQLite backup (nhất quán, gồm WAL);
    - `state/usage.json`, `state/usage-events.jsonl`, `state/settings.json` (settings chỉ có tên provider/model);
    - `server-*.log`: che khoá và token (`redact`);
    - toàn bộ brain tạm (`brains/`: trợ lý, file đích, đầu ra các lượt làm), kịch bản dry.
    File nguồn KHÔNG bị sửa hay xoá; file hỏng chép nguyên bytes. `required`: tên mục bắt buộc phải có (thiếu là lỗi).
    `fault` (chỉ test): hàm(tên) -> True để giả lập lỗi khi chép mục đó. Trả {"ok", "dest", "items"}."""
    import tempfile
    base, dest_root = Path(base), Path(dest_root)
    dest = dest_root / "sandbox"
    i = 2
    while os.path.exists(_xp(dest)):
        dest = dest_root / f"sandbox-{i}"
        i += 1
    items = []

    def rec(name, src, fn):
        it = {"name": name, "ok": False}
        try:
            if fault and fault(name):
                raise OSError(f"lỗi giả lập khi chép {name}")
            if not os.path.exists(_xp(src)):
                it.update(missing=True, ok=name not in required, error="" if name not in required else "thiếu")
            else:
                out = fn()
                it.update(ok=True, **(out or {}))
        except Exception as e:  # noqa: BLE001
            it["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        items.append(it)

    def write_new(d, data: bytes):
        os.makedirs(_xp(Path(d).parent), exist_ok=True)
        with open(_xp(d), "xb") as f:
            f.write(data)

    def sqlite_copy(name):
        src = base / "state" / name

        def fn():
            # Backup vào một file tạm đường ngắn (SQLite không dùng đường `\\?\`), rồi chép bytes sang hồ sơ.
            fd, tmp = tempfile.mkstemp(prefix="a5bk-", suffix=".sqlite3")
            os.close(fd)
            try:
                s = sqlite3.connect(Path(src).resolve().as_uri() + "?mode=ro", uri=True)
                try:
                    t = sqlite3.connect(tmp)
                    try:
                        s.backup(t)
                    finally:
                        t.close()
                finally:
                    s.close()
                data = Path(tmp).read_bytes()
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            write_new(dest / "state" / name, data)
            return {"sha256": _sha_bytes(data), "bytes": len(data)}
        rec(name, src, fn)

    def file_copy(name, src, d, transform=None):
        def fn():
            with open(_xp(src), "rb") as f:
                data = f.read()
            if transform:
                data = transform(data.decode("utf-8", errors="replace")).encode("utf-8")
            write_new(d, data)
            return {"sha256": _sha_bytes(data), "bytes": len(data)}
        rec(name, src, fn)

    os.makedirs(_xp(dest), exist_ok=False)
    for name in ("resonance.sqlite3", "conversations.db"):
        sqlite_copy(name)
    for name in ("usage.json", "usage-events.jsonl", "settings.json"):
        file_copy(name, base / "state" / name, dest / "state" / name)
    for log in sorted(base.glob("server-*.log")):
        file_copy(log.name, log, dest / "logs" / log.name, transform=redact)
    if (base / "dry-script.json").exists():
        file_copy("dry-script.json", base / "dry-script.json", dest / "dry-script.json")
    brains = base / "brains"
    if brains.exists():
        for p in sorted(brains.rglob("*")):
            if p.is_file():
                rel = p.relative_to(base).as_posix()
                file_copy(rel, p, dest / rel)
    for name in required:
        if not any(it["name"] == name for it in items):
            items.append({"name": name, "ok": False, "missing": True, "error": "thiếu"})
    return {"ok": all(it["ok"] for it in items), "dest": str(dest), "items": items}


def may_delete_sandbox(mode: str, acceptance: str, preserve: dict, base: Path, out_dir: Path) -> bool:
    """Chỉ dọn sandbox tạm khi: không phải real (real luôn giữ), kết luận là kỹ thuật đạt trọn, bằng chứng đã bảo toàn
    đủ, và thư mục hồ sơ nằm NGOÀI sandbox. Mọi trường hợp khác giữ nguyên để hậu kiểm."""
    try:
        inside = Path(out_dir).resolve().is_relative_to(Path(base).resolve())
    except Exception:  # noqa: BLE001
        inside = True
    return (mode != "real" and acceptance == "pending_content_review" and (preserve or {}).get("ok") is True
            and not inside)


# ───── ghi hồ sơ cuối ─────

# Ca dry chèn lỗi ghi ở pha kết thúc (chỉ dry): tên ca -> file bị chặn.
DRY_FAULTS = {"report_fault": "report", "report_fault_technical": "report", "recovery_fault": "recovery"}


def dry_fault(mode: str, scen: str):
    """Loại file bị chèn lỗi ghi ở pha kết thúc cho ca dry tương ứng; None ở real và mọi ca khác."""
    return DRY_FAULTS.get(scen) if mode == "dry" else None


def finalize_record(rep: dict, mode: str, scen: str, base, out_dir, pres: dict, delete: bool, lc, fault=None) -> bool:
    """Ghi hồ sơ cuối và CHỐT kết luận theo kết quả ghi (review cổng pilot vòng 2). Trả True khi được dọn sandbox.

    Thứ tự: khi giữ sandbox thì ghi `a5-pilot-recovery.txt` TRƯỚC, rồi ghi báo cáo JSON SAU CÙNG. Báo cáo là bản ghi
    cuối nên không bao giờ có một báo cáo còn nói đạt mà file bắt buộc ghi sau nó lại hỏng.

    Lần ghi bắt buộc nào lỗi (khôi phục hay báo cáo): kết luận thành `technical_failed`, `acceptance_why` thêm nguyên nhân
    cụ thể, nhánh giữ nguyên, sandbox GIỮ (`sandbox_kept = true`), không dọn. Báo cáo lỗi thì ghi lại đường khôi phục với
    kết luận mới và thử ghi báo cáo đúng một lần nữa; vẫn lỗi thì báo thất bại và đường sandbox ra stdout và stderr.
    Không gọi engine, không đổi số lượt. Dòng `A5_PILOT` in SAU khi chốt, cùng kết luận và trạng thái giữ sandbox với
    báo cáo (nếu đã ghi được) và mã thoát. `fault` (chỉ dry): "report" hay "recovery", chặn lần ghi tương ứng."""
    import sys as _sys
    base, out_dir = Path(base), Path(out_dir)
    report = out_dir / f"a5-pilot-{mode}-{scen or 'main'}.json"
    recovery = out_dir / "a5-pilot-recovery.txt"
    keep = not delete
    errors = []

    def write(path, text, kind):
        if fault == kind:
            raise PermissionError(f"lỗi giả lập khi ghi {path.name}")
        path.write_text(text, encoding="utf-8", newline="\n")

    def downgrade(step, e):
        msg = f"không ghi được {step}: {type(e).__name__}: {str(e)[:200]}"
        if msg not in errors:
            errors.append(msg)
        rep["acceptance"] = "technical_failed"
        rep["acceptance_why"] = [w for w in (rep.get("acceptance_why") or []) if w != msg] + [msg]
        rep["record_errors"] = list(errors)

    def report_text():
        txt = json.dumps(rep, ensure_ascii=True, indent=2) + "\n"
        for secret in (str(base), str(Path.home())):
            txt = txt.replace(json.dumps(secret)[1:-1], "<path>")
        return txt

    saved = False
    for _attempt in range(2):
        rep["sandbox_kept"] = keep
        if keep:
            try:
                write(recovery, f"sandbox: {base}\nbản sao bằng chứng: {pres.get('dest') or '(không có)'}\n"
                                f"kết luận: {rep.get('acceptance')}\nlý do: "
                                f"{'; '.join(rep.get('acceptance_why') or []) or '-'}\n", "recovery")
            except Exception as e:  # noqa: BLE001
                downgrade("file đường khôi phục", e)
        rep["report_saved"] = True
        try:
            write(report, report_text(), "report")
            saved = True
            break
        except Exception as e:  # noqa: BLE001
            rep["report_saved"] = False
            downgrade("báo cáo cuối", e)
            keep = True
    rep["sandbox_kept"] = keep
    rep["report_saved"] = saved
    if errors:
        line = ("KHÔNG GHI ĐƯỢC HỒ SƠ CUỐI: " + "; ".join(errors) + f" | kết luận: {rep['acceptance']} | "
                f"sandbox giữ tại: {base}")
        print(line)
        print(line, file=_sys.stderr)
    if keep:
        print("A5_PILOT_KEPT " + str(base))
    print("A5_PILOT " + json.dumps({k: rep.get(k) for k in ("mode", "scenario", "acceptance", "branch", "model_turns",
                                                             "ledger_status", "engine_turns_logged",
                                                             "engine_turns_status", "sandbox_kept", "report_saved")},
                                   ensure_ascii=False) + " PRESERVE " + json.dumps((pres or {}).get("ok"))
          + " LEDGER " + json.dumps(lc, ensure_ascii=False))
    return not keep


# ───── kiểm nguồn trước khi có thể gọi model ─────

def preflight_source(root: Path, approved_sha: str) -> dict:
    """HEAD của checkout phải đúng SHA đã duyệt và cây phải SẠCH hoàn toàn (mọi file đã track, kể cả mã sản phẩm và chính
    bộ chạy; không file lạ chưa track). Không đọc được git hay thiếu SHA đã duyệt thì không đạt."""
    out = {"ok": False, "approved": approved_sha or "", "head": "", "dirty": None, "why": ""}
    try:
        out["head"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True, text=True,
                                     timeout=20).stdout.strip()
        por = subprocess.run(["git", "status", "--porcelain"], cwd=str(root), capture_output=True, text=True,
                             timeout=60)
        if por.returncode != 0:
            raise RuntimeError("git status lỗi")
        lines = [ln for ln in por.stdout.splitlines() if ln.strip()]
        out["dirty"] = lines[:50]
    except Exception as e:  # noqa: BLE001
        out["why"] = f"không đọc được git: {type(e).__name__}"
        return out
    if not approved_sha:
        out["why"] = "thiếu SHA đã duyệt"
    elif out["head"] != approved_sha:
        out["why"] = f"HEAD {out['head'][:12]} khác SHA đã duyệt {approved_sha[:12]}"
    elif out["dirty"]:
        out["why"] = f"cây không sạch ({len(out['dirty'])} mục)"
    else:
        out["ok"] = True
    return out
