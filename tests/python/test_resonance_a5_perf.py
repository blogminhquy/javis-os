"""Resonance A5: hiệu năng của đội làm và review (thiết kế A5 mục 14). Không gọi model, dữ liệu tạm, engine giả.

    python tests/run.py resonance_a5_perf -v

1. goal_view của 200 mục tiêu CÓ ĐỘI so với 200 mục tiêu không có đội trên cùng máy: phần đội (một truy vấn goal_team,
   team_calls, reviews theo goal_id) không làm thẻ chậm đi đáng kể. Đo tương đối nên không phụ thuộc tốc độ máy CI.
2. Event loop không bị chặn khi lượt review chạy: pha trước và pha sau (SQLite, băm ảnh chụp, lưu bằng chứng giả lập chậm
   0,2 giây) ở luồng phụ; một timer 10 ms vẫn đúng giờ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
import time
from pathlib import Path

_STATE = Path(tempfile.mkdtemp(prefix="javis-res-a5perf-"))
os.environ["JAVIS_STATE_DIR"] = str(_STATE)
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)

import resonance as R  # noqa: E402
import _resonance_team as T  # noqa: E402

_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info})"))
    if not cond:
        _fails.append(name)


def seed(t, n, prefix):
    ids = []
    for i in range(n):
        it = t.store.add_intent(t.owner, t.sid, 1000 + i, T.USER)
        frame = R.validate_proposal(t.proposal(), T.USER, source_ref=f"{prefix}:{i}")
        g, _ = t.store.create(t.p, it["id"], frame, f"{prefix}:{i}", budget_calls=4,
                              agent_key=t.maker["agent_key"], agent_version=t.maker["config_version"])
        ids.append(g.id)
    return ids


def views(t, ids):
    t0 = time.perf_counter()
    for gid in ids:
        assert R.goal_view(t.store, t.owner, gid, t.brain) is not None
    return time.perf_counter() - t0


plain = T.Team(_STATE, "plain", pair=False)
team = T.Team(_STATE, "team")
ids_plain = seed(plain, 200, "p")
ids_team = seed(team, 200, "t")
check("200 mục tiêu có đội đã gắn đội", all(team.store.goal_team(team.owner, x) for x in ids_team[:5]))
views(plain, ids_plain[:10])
views(team, ids_team[:10])                  # làm nóng
tp = min(views(plain, ids_plain) for _ in range(2))
tt = min(views(team, ids_team) for _ in range(2))
check(f"1 goal_view 200 mục tiêu có đội không chậm hơn đáng kể (có đội {tt:.2f}s, không đội {tp:.2f}s; "
      "ngưỡng 2 lần + 0,5 giây)", tt <= tp * 2 + 0.5, (round(tt, 3), round(tp, 3)))
# Thẻ KHÔNG có đội trên máy dev đã khoảng 50 ms (mức nền của A1 đến A4, không thuộc A5): chỉ đo phần đội THÊM vào.
check("1 phần đội thêm dưới 25 ms mỗi thẻ", (tt - tp) / 200 < 0.025, round((tt - tp) / 200 * 1000, 1))

# 2. Event loop không bị chặn trong lúc lượt review chạy.
t = T.Team(_STATE, "loop")
g = t.create()
t.wake(g)                                   # bản đầu, hẹn review
_put = t.ev.put


def slow_put(goal, label, text, meta):
    time.sleep(0.2)                         # giả lập lưu bằng chứng chậm (đồng bộ, như đĩa chậm)
    return _put(goal, label, text, meta)


t.ev.put = slow_put


async def _run():
    late = []
    stop = asyncio.Event()

    async def ticker():
        while not stop.is_set():
            t0 = time.perf_counter()
            await asyncio.sleep(0.01)
            late.append(time.perf_counter() - t0 - 0.01)
    tk = asyncio.create_task(ticker())
    await asyncio.sleep(0.03)
    await R.advance(g.id, {"kind": "wake"}, t.deps())
    stop.set()
    await tk
    return late


late = asyncio.run(_run())
check("2 lượt review chạy xong (pass được ghi)", t.reviews(g) and t.reviews(g)[0]["verdict"] == "pass")
check("2 timer 10 ms đúng giờ trong lúc review lưu bằng chứng chậm 0,2 giây (trễ tối đa < 0,1 giây, có mẫu đo)",
      len(late) >= 5 and max(late) < 0.1, (len(late), round(max(late) if late else -1, 3)))

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    raise SystemExit(1)
print("\nOK")
