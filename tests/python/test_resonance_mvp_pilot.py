"""Resonance M3: pilot thật một mục tiêu có sự kiện tiếp tục, qua đường host thật của Javis.

    JAVIS_RESONANCE_PILOT=1 JAVIS_RESONANCE_PILOT_SETTINGS=<settings.json thật> python tests/run.py resonance_mvp_pilot -v

Không đặt JAVIS_RESONANCE_PILOT=1 thì bỏ qua (CI không gọi model). Khi chạy:
- JAVIS_STATE_DIR tạm; chỉ chép các ô CHỌN engine từ settings.json thật (không chép khoá).
- Brain tạm với dữ liệu mô phỏng; không đụng brain hay tài khoản thật.
- Đi qua main._resonance_tick (đúng nhịp scheduler), main._resonance_engine (engine việc nền đã chọn, chỉ chữ,
  không chuỗi dự phòng) và main._RESONANCE_EVIDENCE (EvidenceStore thật). Kênh báo được thay bằng bộ ghi lại để
  không gửi gì ra ngoài.
- Hạn mức của mục tiêu 3 lượt; kịch bản cần 2 lượt gọi model thật.
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
    print("pilot thật M3: bỏ qua (đặt JAVIS_RESONANCE_PILOT=1 để chạy)")
    print("\nOK")
    sys.exit(0)

_STATE = tempfile.mkdtemp(prefix="javis-resonance-m3p-")
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


BRAIN = Path(tempfile.mkdtemp(prefix="brain-pilot-")).resolve()
(BRAIN / "Javis").mkdir(parents=True)
(BRAIN / "Javis" / "resonance.json").write_text('{"enabled": true}', encoding="utf-8")
(BRAIN / "Notes").mkdir()
(BRAIN / "Notes" / "ghi-chu-cu.md").write_text("Ghi chú cũ, không được xoá.\n", encoding="utf-8")
KEY = main._brain_key(str(BRAIN))
P = RS.Principal("agent", "javis", KEY)

USER1 = ("Dữ liệu mô phỏng, không phải việc thật. Duy trì giúp anh ghi chú Inbox/viec-tuan.md liệt kê việc đang dở: "
         "gửi báo giá cho khách B, kiểm kho bút bi, đặt lịch họp nhóm thứ Năm. Đừng xoá ghi chú cũ.")
USER2 = "Thêm việc: gia hạn tên miền trước cuối tháng."
CRIT = lambda words: [{"description": "Ghi chú việc đang dở có đủ các việc", "evaluator": "artifact_contract",  # noqa: E731
                       "params": {"path": "Inbox/viec-tuan.md", "min_chars": 60, "must_contain": words}}]

store = main._resonance_store()
deps0 = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "tạo mục tiêu không gọi model"}),
                   budget=R.CallBudget(0), store=store)
g = asyncio.run(R.form_goal(R.message_ref("pilot", 1), {
    "principal": P, "brain_root": KEY, "session_id": "pilot", "message_id": 1, "user_text": USER1,
    "constraints": ["Đừng xoá ghi chú cũ"], "budget_calls": 3,
    "proposal": {"understanding": "Duy trì ghi chú Inbox/viec-tuan.md liệt kê việc đang dở",
                 "criteria": CRIT(["báo giá", "kho", "họp"]), "relevant_quote": "Duy trì giúp anh ghi chú Inbox/viec-tuan.md",
                 "horizon": {"kind": "maintain"}, "mode": "maintain", "constraints": ["Đừng xoá ghi chú cũ"],
                 "guards": [{"description": "Ghi chú cũ vẫn còn", "evaluator": "artifact_contract",
                             "params": {"path": "Notes/ghi-chu-cu.md"}}]}}, deps0))

sent = []


async def _capture(owner_chat, text, **kw):
    sent.append({"chat": owner_chat, "text": text})
    return True, ""

main._notify_owner = _capture          # không gửi gì ra ngoài trong pilot
t0 = time.time()
asyncio.run(main._resonance_tick())     # nhịp 1: mục tiêu mới tới hạn ngay
t1 = time.time()
acts1 = store.actions(P, g.id)
a1 = (store.assessments(P, g.id) or [{}])[-1]
check("nhịp 1: đúng một lượt làm việc với engine thật, receipt succeeded",
      [x["status"] for x in acts1 if x["kind"] == "work"] == ["succeeded"])
check("nhịp 1: sản phẩm có trong brain và host kiểm đạt theo tiêu chí", (BRAIN / "Inbox" / "viec-tuan.md").is_file()
      and a1.get("verdict") == "met")
check("nhịp 1: mục tiêu duy trì vẫn active, có lịch xem lại có giới hạn",
      store.get(P, g.id).status == "active" and any(w["kind"] == "work" for w in store.wakes(P, g.id)))

# Sự kiện tiếp tục: người dùng bổ sung một việc. Sau đó GIẢ LẬP KHỞI ĐỘNG LẠI: mở kho mới, bỏ đối tượng cũ.
R.revise_goal(store, P, g.id, 1, {"relevant_quote": "gia hạn tên miền",
                                   "criteria": CRIT(["báo giá", "kho", "họp", "tên miền"])},
              {"message_ref": R.message_ref("pilot", 2), "session_id": "pilot", "message_id": 2, "user_text": USER2})
main._RESONANCE_STORE = None
store = main._resonance_store()
asyncio.run(main._resonance_tick())     # nhịp 2: làm tiếp theo revision 2
t2 = time.time()
asyncio.run(main._resonance_tick())     # nhịp 3: không có gì tới hạn
acts = store.actions(P, g.id)
work = [x for x in acts if x["kind"] == "work"]
a2 = (store.assessments(P, g.id) or [{}])[-1]
final_text = (BRAIN / "Inbox" / "viec-tuan.md").read_text(encoding="utf-8")
check("nhịp 2 sau khởi động lại: thêm đúng một lượt, revision 2 đạt", len(work) == 2 and work[-1]["revision"] == 2
      and a2.get("verdict") == "met" and a2.get("revision") == 2)
check("nhịp 2: sản phẩm có việc mới và vẫn giữ việc cũ", all(w in final_text.lower() for w in
                                                              ("báo giá", "kho", "họp", "tên miền")))
check("nhịp 3: không có lịch tới hạn thì không gọi thêm", len([x for x in store.actions(P, g.id) if x["kind"] == "work"]) == 2)
check("hạn mức: đã dùng đúng 2/3 lượt", store.get(P, g.id).calls_used == 2)
check("ghi chú cũ (guard) còn nguyên", (BRAIN / "Notes" / "ghi-chu-cu.md").is_file())
check("không em dash trong file brain", "—" not in final_text)
ev_ok = []
for e in store.evidence_for(P, g.id, 2):
    v = main._RESONANCE_EVIDENCE.valid(e["evidence_id"])
    ev_ok.append(bool(v) and v["content_hash"] == e["content_hash"])
check("bằng chứng revision 2 đọc lại được từ EvidenceStore thật, hash khớp", bool(ev_ok) and all(ev_ok))
for r in work:
    rc = r["receipt"]
    check(f"receipt {r['id']}: đúng provider đã chọn, không gọi công cụ, hash khớp file trên đĩa",
          rc.get("engine", {}).get("provider") == rc.get("engine", {}).get("requested_provider")
          and rc.get("tool_calls_observed") == 0
          and rc.get("output_sha256") == hashlib.sha256(Path(rc["output_ref"]).read_bytes()).hexdigest())


def _clean(rc):
    rc = dict(rc)
    if rc.get("output_ref"):
        rc["output_ref"] = Path(rc["output_ref"]).name
    return rc


try:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True, timeout=10).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "server"], cwd=str(ROOT), capture_output=True,
                                text=True, timeout=10).stdout.strip())
except Exception:  # noqa: BLE001
    head, dirty = "", None
rep = {"commit": head, "server_dirty": dirty, "user_messages": [USER1, USER2],
       "seconds": {"tick1": round(t1 - t0, 1), "tick2": round(t2 - t1, 1)},
       "work_receipts": [_clean(x["receipt"]) for x in work],
       "publish_actions": [{"status": x["status"], **{k: x["receipt"].get(k) for k in ("path", "sha256")}}
                           for x in acts if x["kind"] == "publish"],
       "assessments": [{k: a.get(k) for k in ("revision", "verdict", "rationale", "guards")}
                       for a in store.assessments(P, g.id)],
       "wakes_after": [{k: w[k] for k in ("kind", "reason")} for w in store.wakes(P, g.id)],
       "calls_used": store.get(P, g.id).calls_used, "budget_calls": store.get(P, g.id).budget_calls,
       "notices": sent, "final_output": final_text}
print("PILOT_REPORT " + json.dumps(rep, ensure_ascii=False)[:2000])
outp = os.environ.get("JAVIS_RESONANCE_PILOT_OUT")
if outp:
    Path(outp).write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
