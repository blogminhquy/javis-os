"""Resonance M5: pilot thật một phép thử cải thiện, qua engine việc nền đã chọn và EvidenceStore thật.

    JAVIS_RESONANCE_PILOT=1 JAVIS_RESONANCE_PILOT_SETTINGS=<settings.json thật> python tests/run.py resonance_mvp_trial_pilot -v

Không đặt JAVIS_RESONANCE_PILOT=1 thì bỏ qua (CI không gọi model). Khi chạy:
- JAVIS_STATE_DIR tạm; chỉ chép các ô CHỌN engine từ settings.json thật (không chép khoá).
- Brain tạm, dữ liệu mô phỏng từ tests/fixtures/resonance/mvp_cases.json (mục "pilot").
- Engine là main._resonance_engine (engine việc nền đã chọn, chỉ chữ, không chuỗi dự phòng), bằng chứng là
  main._RESONANCE_EVIDENCE. Không đăng gì vào brain, không gửi gì ra ngoài.
- Hạn mức mục tiêu 8 lượt, phần khám phá 4: phép thử cần đúng 4 lượt gọi model thật (2 tình huống x 2 cách làm);
  tình huống chỉ người dùng chấm được không chạy.
Kiểm CỨNG các tính chất của host (hạn mức, receipt, bằng chứng, không đăng, không đổi cách làm khi chưa eligible).
Kết quả chấm của model chỉ GHI LẠI, không ép: model thật có thể cho kết quả khác kỳ vọng ghi trong fixture.
JAVIS_RESONANCE_PILOT_OUT: nơi ghi báo cáo JSON (không có đường dẫn cá nhân).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PILOT = os.environ.get("JAVIS_RESONANCE_PILOT") == "1"
if not PILOT:
    print("pilot thật M5: bỏ qua (đặt JAVIS_RESONANCE_PILOT=1 để chạy)")
    print("\nOK")
    sys.exit(0)

_STATE = tempfile.mkdtemp(prefix="javis-resonance-m5p-")
os.environ["JAVIS_STATE_DIR"] = _STATE
src = os.environ.get("JAVIS_RESONANCE_PILOT_SETTINGS", "")
if not src or not Path(src).is_file():
    print("FAIL pilot: thiếu JAVIS_RESONANCE_PILOT_SETTINGS trỏ tới settings.json thật")
    sys.exit(1)
_m = (json.loads(Path(src).read_text(encoding="utf-8")).get("model") or {})
Path(_STATE, "settings.json").write_text(json.dumps({"model": {k: _m[k] for k in ("auxiliary", "main", "engine",
                                                                                   "claude_model") if k in _m}},
                                                    ensure_ascii=False), encoding="utf-8", newline="\n")

import main  # noqa: E402  - nạp SAU khi JAVIS_STATE_DIR tạm đã đặt
import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


FIX = json.loads((Path(ROOT) / "tests" / "fixtures" / "resonance" / "mvp_cases.json").read_text(encoding="utf-8"))
PLAN = FIX["pilot"]
BRAIN = Path(tempfile.mkdtemp(prefix="brain-m5p-")).resolve()
(BRAIN / "Javis").mkdir(parents=True)
(BRAIN / "Javis" / "resonance.json").write_text('{"enabled": true}', encoding="utf-8")
KEY = main._brain_key(str(BRAIN))
P = RS.Principal("agent", "javis", KEY)
store = main._resonance_store()
d0 = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "tạo mục tiêu không gọi model"}),
                budget=R.CallBudget(0), store=store)
g = asyncio.run(R.form_goal(R.message_ref("pilot5", 1), {
    "principal": P, "brain_root": KEY, "session_id": "pilot5", "message_id": 1,
    "user_text": FIX["goal"]["user_text"], "constraints": [], "budget_calls": 8,
    "proposal": dict(FIX["goal"]["proposal"])}, d0))
store.clear_wake(P, g.id)        # pilot chỉ chạy phép thử, không để scheduler làm lượt việc nào
deps = main._resonance_deps(KEY)
cases = {"cases": [c for c in FIX["cases"] if c["id"] in PLAN["case_ids"]]}

t0 = time.time()
res = asyncio.run(R.compare_methods(g.id, PLAN["baseline"], PLAN["candidate"], cases, deps))
secs = round(time.time() - t0, 1)
g2 = store.get(P, g.id)
trial_acts = [a for a in store.actions(P, g.id) if a["kind"] == "trial"]
calls = res["usage"]["baseline"]["calls"] + res["usage"]["candidate"]["calls"]
check("phép thử được tạo trong phần khám phá, đúng revision", res["created"] and res["revision"] == g.revision)
check("tối đa 4 lượt gọi model thật, đúng bằng số lượt tính vào hạn mức", calls <= 4 and g2.calls_used == calls
      and len(trial_acts) == calls)
h2 = [r for r in res["results"] if r["case_id"] == "h2"]
check("tình huống chỉ người dùng chấm được (h2) không chạy, ghi unknown ở cả hai bên",
      len(h2) == 1 and h2[0]["baseline"].get("skipped") is True
      and h2[0]["baseline"]["verdict"] == h2[0]["candidate"]["verdict"] == "unknown"
      and not any(a["intent"].get("case_id") == "h2" for a in trial_acts))
for a in trial_acts:
    rc = a["receipt"]
    if rc.get("status") == "succeeded":
        check(f"receipt {a['id']} ({a['intent'].get('arm')}/{a['intent'].get('case_id')}): đúng provider đã chọn, "
              f"không gọi công cụ, hash khớp file trên đĩa",
              rc.get("engine", {}).get("provider") == rc.get("engine", {}).get("requested_provider")
              and rc.get("tool_calls_observed") == 0
              and rc.get("output_sha256") == hashlib.sha256(Path(rc["output_ref"]).read_bytes()).hexdigest())
ev_ok = [bool(main._RESONANCE_EVIDENCE.valid(e)) for e in res["evidence_refs"]]
check("bằng chứng của phép thử đọc lại được từ EvidenceStore thật", all(ev_ok))
check("phép thử không đăng gì vào brain", not (BRAIN / "Inbox").exists())
check("cách làm chỉ đổi khi eligible",
      (R.effective_method(g2) == PLAN["candidate"]) == (res["verdict"] == "eligible" and res["applied"]))
check("kết quả phép thử được lưu (kể cả khi ứng viên thua)",
      store.experiments(P, g.id) and store.experiments(P, g.id)[0]["verdict"] == res["verdict"])


def _out(a):
    rc = a["receipt"]
    try:
        return Path(rc["output_ref"]).read_text(encoding="utf-8") if rc.get("output_ref") else ""
    except OSError:
        return ""


try:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True, timeout=10).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "server"], cwd=str(ROOT), capture_output=True,
                                text=True, timeout=10).stdout.strip())
except Exception:  # noqa: BLE001
    head, dirty = "", None
rep = {"commit": head, "server_dirty": dirty, "seconds": secs, "engine": (trial_acts[0]["receipt"].get("engine")
                                                                         if trial_acts else None),
       "baseline": PLAN["baseline"], "candidate": PLAN["candidate"], "verdict": res["verdict"], "reason": res["reason"],
       "applied": res["applied"], "rubric_hash": res["rubric_hash"], "usage": res["usage"],
       "calls_used": g2.calls_used, "budget_calls": g2.budget_calls, "explore_used": g2.explore_used,
       "results": [{"case_id": r["case_id"], "split": r["split"],
                    **{arm: {k: r[arm].get(k) for k in ("verdict", "reason", "skipped", "output_sha256", "error_code")}
                       for arm in ("baseline", "candidate")}} for r in res["results"]],
       "outputs": [{"case_id": a["intent"].get("case_id"), "arm": a["intent"].get("arm"),
                    "method": a["intent"].get("method"), "status": a["status"],
                    "usage": a["receipt"].get("usage"), "text": _out(a)} for a in trial_acts]}
print("PILOT_REPORT " + json.dumps({k: rep[k] for k in ("verdict", "reason", "applied", "usage", "results")},
                                   ensure_ascii=False)[:3000])
outp = os.environ.get("JAVIS_RESONANCE_PILOT_OUT")
if outp:
    # ensure_ascii: đầu ra của model có thể có ký tự gạch dài, repo không cho ký tự đó xuất hiện nguyên dạng.
    Path(outp).write_text(json.dumps(rep, ensure_ascii=True, indent=2) + "\n", encoding="utf-8", newline="\n")

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
