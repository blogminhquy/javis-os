"""Snapshot Kanban: bỏ N+1, và đẩy khỏi event loop mà KHÔNG làm mirror thiu.

    python tests/run.py kanban_snapshot     (KHÔNG mạng)

Bối cảnh 0.9.240: _snapshot lấy list_tasks(limit=5000) rồi gọi list_events cho TỪNG task -
đúng khuôn N+1 - rồi serialize và ghi file, tất cả ĐỒNG BỘ trên event loop. Nó chạy sau mỗi
lần giao việc, mỗi lần worker xong, mỗi nhịp dọn 5 giây, và ở 10 route handler async.
Hiện bảng đang rỗng nên chưa ai thấy, nhưng chi phí tăng tuyến tính tới trần 5000.

Test giữ hai thứ đối nghịch nhau:
- NHANH: một truy vấn thay vì N, và không khoá event loop.
- ĐÚNG: đẩy ra thread rồi thì hai lần snapshot song song có thể ghi ĐÈ NGƯỢC nhau, để lại
  mirror thiu. Đó là lý do có khoá theo brain, và test phải chứng minh khoá hoạt động.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-kbsnap-"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi import FastAPI          # noqa: E402,F401
from tasks import TasksDeps, TasksFeature   # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


TMP = Path(tempfile.mkdtemp(prefix="javis-kbsnap-brain-"))
BRAIN = TMP / "Brain X"
BRAIN.mkdir(parents=True, exist_ok=True)


def _atomic(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


async def _workflow(*_a, **_k):
    if False:
        yield {}


feat = TasksFeature(TasksDeps(
    brain_root=lambda v: str(BRAIN),
    atomic_write_text=_atomic,
    execute_workflow=_workflow,
    workflows_dir=lambda b: BRAIN / "workflows",
    build_system_prompt=lambda b: "system",
    aux_model=lambda: None,
    safe_tools=["Read"],
    state_dir=TMP / "state",
    scheduler_brains=lambda: [str(BRAIN)],
))
store = feat.store
ROOT = str(BRAIN.resolve())

# ---- Dựng bảng có việc + nhật ký ----
N_TASK, N_EVENT = 120, 5
ids = []
for i in range(N_TASK):
    tid = store.enqueue(ROOT, f"Việc {i}", f"làm việc {i}", "auto", 2, None,
                        False, "user", "", "auto", "auto", "", "todo")
    ids.append(tid)
    for k in range(N_EVENT):
        store._event(tid, "note", f"ghi chú {i}-{k}")

check(f"dựng được {N_TASK} việc", len(store.list_tasks(ROOT, include_archived=True, limit=5000)) == N_TASK)

# ---- 1. list_events_bulk phải TRÙNG KHỚP từng cái với list_events ----
bulk = store.list_events_bulk(ids, 20)
lech = [t for t in ids if bulk.get(t) != store.list_events(t, 20)]
check(f"bulk khớp tuyệt đối với gọi lẻ trên cả {N_TASK} việc"
      + (f" (LỆCH {len(lech)})" if lech else ""), not lech)

# ---- 2. Trần mỗi task được tôn trọng, thứ tự giữ nguyên cũ -> mới ----
bulk2 = store.list_events_bulk(ids[:3], 2)
check("trần 2 sự kiện mỗi việc được tôn trọng",
      all(len(v) == 2 for v in bulk2.values()))
mot = bulk2[ids[0]]
check("thứ tự trong mỗi việc là cũ -> mới (giống list_events)",
      [e["message"] for e in mot] == [e["message"] for e in store.list_events(ids[0], 2)])

# ---- 3. Cắt lô: phải đúng cả khi vượt 500 id một lượt ----
nhieu = ids * 6          # 720 id (có lặp) -> ép đi qua nhiều lô
b3 = store.list_events_bulk(nhieu, 20)
check(f"vượt 500 id một lượt vẫn trả đủ ({len(b3)} khoá cho {len(set(nhieu))} id phân biệt)",
      len(b3) == len(set(nhieu)))
check("id không tồn tại trả danh sách rỗng chứ không thiếu khoá",
      store.list_events_bulk(["khong-co-that"], 20) == {"khong-co-that": []})
check("danh sách id rỗng trả dict rỗng", store.list_events_bulk([], 20) == {})

# ---- 4. Đếm số truy vấn: N+1 phải biến mất ----
# sqlite3.Connection.execute chỉ đọc, không vá được -> dùng set_trace_callback,
# đây cũng là cách đo trung thực hơn vì nó bắt MỌI câu lệnh thật sự chạy xuống engine.
dem = {"n": 0}


def theo_doi(sql):
    if "task_events" in sql:
        dem["n"] += 1


store._db.set_trace_callback(theo_doi)
try:
    dem["n"] = 0
    feat._snapshot(ROOT)
    n_truy_van = dem["n"]
finally:
    store._db.set_trace_callback(None)
check(f"1 snapshot của {N_TASK} việc chỉ tốn {n_truy_van} truy vấn task_events (trước là {N_TASK})",
      n_truy_van <= 2)

# ---- 5. Mirror ghi ra đúng nội dung ----
mirror = json.loads((BRAIN / "Javis" / "kanban.json").read_text(encoding="utf-8"))
check(f"mirror có đủ {N_TASK} việc", len(mirror["tasks"]) == N_TASK)
co_log = [t for t in mirror["tasks"] if t.get("log")]
check(f"mọi việc đều có nhật ký trong mirror ({len(co_log)}/{N_TASK})", len(co_log) == N_TASK)
# N_EVENT ghi chú TỰ THÊM, cộng 1 sự kiện 'created' do chính enqueue sinh ra.
check(f"mỗi việc giữ đủ {N_EVENT + 1} dòng nhật ký ({N_EVENT} ghi chú + 1 'created' của enqueue)",
      all(len(t["log"]) == N_EVENT + 1 for t in mirror["tasks"]))

# ---- 6. _asnapshot không khoá event loop ----
async def do_tre(chay):
    tre = []

    async def nhip():
        while True:
            t = time.perf_counter()
            await asyncio.sleep(0.005)
            tre.append((time.perf_counter() - t) * 1000)

    tk = asyncio.create_task(nhip())
    await asyncio.sleep(0.05)
    await chay()
    # BẮT BUỘC nhường loop trước khi huỷ nhịp: hàm đồng bộ không có điểm await nào nên
    # nhịp tim chỉ ghi được con số trễ SAU khi loop chạy lại. Huỷ ngay là mất đúng phép
    # đo cần đo, và test sẽ xanh cho cả hai đường - tức vô nghĩa.
    await asyncio.sleep(0.02)
    tk.cancel()
    try:
        await tk
    except asyncio.CancelledError:
        pass
    return max(tre) if tre else 0.0


async def _duong_that():
    return await feat._asnapshot(ROOT)


async def _duong_dong_bo():
    return feat._snapshot(ROOT)      # hành vi TRƯỚC 0.9.240: chạy thẳng trên loop


# Ép bước GHI chậm một cách TẤT ĐỊNH thay vì trông vào 120 việc là đủ nặng. Bản trước
# dùng ngưỡng tương đối và ĐỎ trên CI: máy runner nhanh nên snapshot chỉ mất 20ms, không
# đủ biên để phân biệt. Việc nặng bao nhiêu phụ thuộc máy; độ trễ do sleep thì không.
DO_TRE_GIA = 0.15
_ghi_that = feat.deps.atomic_write_text


def _ghi_cham(path, text):
    time.sleep(DO_TRE_GIA)      # giả lập đĩa chậm / bảng việc lớn
    _ghi_that(path, text)


try:
    feat.deps.atomic_write_text = _ghi_cham
    tre_async = asyncio.run(do_tre(_duong_that))
    tre_sync = asyncio.run(do_tre(_duong_dong_bo))
finally:
    feat.deps.atomic_write_text = _ghi_that

nguong = DO_TRE_GIA * 1000
print(f"     (mỗi lần ghi mất {nguong:.0f} ms | độ trễ nhịp tim: qua to_thread "
      f"{tre_async:.0f} ms, gọi thẳng trên loop {tre_sync:.0f} ms)")
# Đối chứng: không có bước này thì con số bên trên có thể nhỏ vì việc quá nhẹ chứ không
# phải vì code đúng.
check(f"phép đo có răng: gọi thẳng trên loop khoá loop >= {nguong:.0f} ms ({tre_sync:.0f} ms)",
      tre_sync >= nguong)
# Ngưỡng đo THEO ĐƯỜNG ĐỒNG BỘ chứ không phải một con số cứng, và đây là chỗ test này đã đỏ
# oan hai lần theo hai hướng ngược nhau:
#
#   - Ngưỡng tương đối mà KHÔNG ép sleep: runner nhanh nên snapshot chỉ mất 20ms, hai đường
#     gần bằng nhau, phép đo không phân biệt được gì. (Đã chữa bằng DO_TRE_GIA ở trên.)
#   - Ngưỡng CỨNG 75ms: máy đang chạy cả bộ test thì nhịp tim của event loop trễ vì TRANH CPU,
#     không phải vì bị khoá. Đo được 133ms rồi đỏ, trong khi code không có gì sai - CI đã đỏ
#     oan đúng kiểu này một lần (2026-08-13).
#
# So với `tre_sync` thì cả hai bệnh cùng hết: sleep ép sẵn bảo đảm có biên để so, còn khi máy
# tải nặng thì HAI con số cùng phình lên nên tỉ lệ giữa chúng vẫn nói đúng một chuyện - đường
# thật có nhả event loop ra hay không. Điều kiện "có răng" ngay trên đã chốt tre_sync >= 150ms
# nên phép chia này không bao giờ rỗng nghĩa.
check(f"đường thật KHÔNG khoá loop dù mỗi lần ghi mất {nguong:.0f} ms "
      f"({tre_async:.0f} ms, phải dưới nửa đường đồng bộ {tre_sync / 2:.0f} ms)",
      tre_async < tre_sync / 2)

# ---- 7. Snapshot song song phải NỐI TIẾP, không ghi đè ngược ----
# Không có khoá thì lần chạy CŨ có thể hạ cánh sau lần MỚI và để lại mirror thiu.
dang_chay = {"n": 0, "max": 0}
_snap_that = feat._snapshot


def _snap_cham(root):
    dang_chay["n"] += 1
    dang_chay["max"] = max(dang_chay["max"], dang_chay["n"])
    time.sleep(0.05)
    _snap_that(root)
    dang_chay["n"] -= 1


async def chay_song_song():
    feat._snapshot = _snap_cham
    try:
        await asyncio.gather(*(feat._asnapshot(ROOT) for _ in range(6)))
    finally:
        feat._snapshot = _snap_that


asyncio.run(chay_song_song())
check(f"6 snapshot cùng lúc chạy NỐI TIẾP, không chồng nhau (đỉnh {dang_chay['max']})",
      dang_chay["max"] == 1)

# ---- 8. Brain khác nhau KHÔNG chặn nhau (khoá theo brain, không phải khoá toàn cục) ----
BRAIN2 = TMP / "Brain Y"
BRAIN2.mkdir(parents=True, exist_ok=True)
ROOT2 = str(BRAIN2.resolve())
feat._snap_locks.clear()
asyncio.run(feat._asnapshot(ROOT))
asyncio.run(feat._asnapshot(ROOT2))
check("khoá tách riêng theo từng brain", set(feat._snap_locks) == {ROOT, ROOT2})

print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
