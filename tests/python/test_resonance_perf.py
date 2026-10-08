"""Resonance: hiệu năng thẻ mục tiêu (audit tốc độ 08/10/2026). Không gọi model, dữ liệu tạm.

    python tests/run.py resonance_perf -v

1. goal_view đọc CÓ GIỚI HẠN (đánh giá mới nhất có kết quả, lượt làm mới nhất của revision, 8 dòng thời gian,
   3 phép thử) mà kết quả GIỐNG HỆT cách cũ đọc cả lịch sử rồi cắt. So trên lịch sử dài có nhiều revision, nhiều loại
   hành động, đánh giá không có kết quả xen giữa.
2. API thẻ không giữ event loop: goal_view chậm (giả lập đọc đĩa chậm) chạy ở luồng phụ, một timer 10 ms vẫn đúng giờ
   khi có nhiều GET đồng thời.
3. Header Server-Timing có trên response HTTP (để tách thời gian Javis xử lý với thời gian đi qua proxy).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-perf-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402

_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info})"))
    if not cond:
        _fails.append(name)


BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-perf-")).resolve())
P = RS.Principal("agent", "javis", BRAIN)
OWNER = RS.Principal("owner", "owner", BRAIN)
store = RS.GoalStore(Path(_STATE) / "resonance.sqlite3")
FRAME = {"understanding": "Ghi chú", "criteria": [
    {"id": "c1", "description": "Có ghi chú", "evaluator": "artifact_contract", "params": {"path": "Docs/a.md"}},
    {"id": "c2", "description": "Anh duyệt", "evaluator": "human_confirmation", "params": {}}],
    "constraints": [], "guards": [], "mode": "achieve", "stage": "delivery"}
it = store.add_intent(P, "s", 1, "Viết giúp anh ghi chú")
g, _ = store.create(P, it["id"], FRAME, "k1", session_id="s", budget_calls=50)
(Path(BRAIN) / "Docs").mkdir()
(Path(BRAIN) / "Docs" / "a.md").write_text("# Ghi chú\n", encoding="utf-8")

# Lịch sử dài: revision 1 rồi 2, hành động xen loại, đánh giá có và không có kết quả, nhiều phép thử.
for rev in (1, 2):
    if rev == 2:
        g = store.revise(P, g.id, 1, FRAME, "sửa")
    for i in range(30):
        a = store.begin_action(P, g.id, rev, "work" if i % 3 else "publish", lease_until=time.time() + 60)
        store.finish_action(P, a["id"], "succeeded" if i % 4 else "failed",
                            {"output_ref": str(Path(BRAIN) / "Docs" / "a.md"), "error_code": "" if i % 4 else "x"})
    for i in range(60):
        store.add_assessment(P, {"goal_id": g.id, "revision": rev, "verdict": "unknown", "evaluated_at": i,
                                 "criterion_results": ([{"id": "c1", "verdict": "met" if i % 2 else "not_met",
                                                         "reason": f"lần {i}"}] if i % 5 else [])})
for i in range(5):
    store.begin_experiment(P, g.id, 2, "work.v1", "work.checklist.v1", 1, 50, {"i": i})


def reference_view(st, principal, goal_id, brain_root):
    """Cách cũ (0.86.2): đọc cả lịch sử rồi chọn, cắt trong Python."""
    gg = st.get(principal, goal_id)
    last = next((a for a in reversed(st.assessments(principal, goal_id))
                 if a.get("revision") == gg.revision and a.get("criterion_results")), None)
    acts = st.actions(principal, goal_id)
    out = next((x for x in reversed(acts) if x["kind"] == "work" and x["status"] == "succeeded"
                and x["revision"] == gg.revision), None)
    return {"results": {r.get("id"): r for r in (last or {}).get("criterion_results") or []},
            "out_id": (out or {}).get("id"),
            "timeline": [(x["kind"], x["status"], x["revision"], x["created_at"]) for x in acts[-8:]],
            "experiments": [e["id"] for e in st.experiments(principal, goal_id)[:3]]}


ref = reference_view(store, OWNER, g.id, BRAIN)
v = R.goal_view(store, OWNER, g.id, BRAIN)
check("1 đánh giá dùng cho tiêu chí host kiểm: đúng bản mới nhất có kết quả của revision hiện tại",
      next(c for c in v["criteria"] if c["id"] == "c1")["reason"] == ref["results"]["c1"]["reason"])
check("1 dòng thời gian: đúng 8 hành động cuối, đúng thứ tự",
      [(x["kind"], x["status"], x["revision"], x["at"]) for x in v["timeline"]] == ref["timeline"])
check("1 phép thử: đúng 3 phép thử mới nhất", [e["id"] for e in v["experiments"]] == ref["experiments"])
check("1 lượt làm mới nhất của revision: khớp", store.latest_action(
    OWNER, g.id, "work", status="succeeded", revision=g.revision)["id"] == ref["out_id"])
check("1 artifact_ref là hash bytes hiện tại của file sản phẩm (không đổi cách tính)",
      v["artifact_ref"] == R._sha((Path(BRAIN) / "Docs" / "a.md").read_bytes()))
check("1 recent_actions bằng actions()[-8:]", [x["id"] for x in store.recent_actions(OWNER, g.id, 8)]
      == [x["id"] for x in store.actions(OWNER, g.id)[-8:]])
check("1 last_assessment_with_results: None khi revision chưa có đánh giá có kết quả",
      store.last_assessment_with_results(OWNER, g.id, 99) is None)
check("1 đọc có giới hạn vẫn lọc theo brain", store.latest_action(RS.Principal("owner", "owner", "/khac"), g.id, "work")
      is None and store.recent_actions(RS.Principal("owner", "owner", "/khac"), g.id, 8) == [])

# ───────────── 2. API thẻ không giữ event loop ─────────────
import main  # noqa: E402
import httpx  # noqa: E402

_real_view = R.goal_view


def _slow_view(*a, **kw):
    time.sleep(0.2)          # giả lập đọc SQLite/băm file chậm: chặn luồng đang chạy nó
    return {"goal_id": "g_x", "revision": 1}


R.goal_view = _slow_view


async def _probe():
    late = []

    async def timer():
        for _ in range(10):
            t = time.perf_counter()
            await asyncio.sleep(0.01)
            late.append(time.perf_counter() - t - 0.01)

    tr = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=tr, base_url="http://127.0.0.1:8080") as cl:
        tm = asyncio.create_task(timer())
        t0 = time.perf_counter()
        rs = await asyncio.gather(*[cl.get(f"/goals/g_x", params={"brain": BRAIN}) for _ in range(5)])
        total = time.perf_counter() - t0
        await tm
    return rs, late, total


rs, late, total = asyncio.run(_probe())
R.goal_view = _real_view
check("2 GET /goals/{id} chạy goal_view ở luồng phụ: trả 200", all(r.status_code == 200 for r in rs),
      [r.status_code for r in rs])
check("2 timer 10 ms vẫn đúng giờ trong lúc 5 GET đồng thời mỗi cái chặn 0,2 giây (trễ tối đa < 0,1 giây)",
      max(late) < 0.1, round(max(late), 3))
check("2 năm GET chạy song song (tổng < 0,8 giây thay vì 1 giây nếu xếp hàng trên event loop)", total < 0.8,
      round(total, 3))

# ───────────── 3. Server-Timing ─────────────
from fastapi.testclient import TestClient  # noqa: E402
r = TestClient(main.app, base_url="http://127.0.0.1:8080").get("/health")
st_h = r.headers.get("server-timing", "")
check("3 response có Server-Timing: app;dur=<ms>", st_h.startswith("app;dur="), st_h)

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
