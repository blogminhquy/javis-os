"""GET /brains: đếm note có TRẦN, chạy ngoài event loop, không đếm thư mục hệ thống.

    python tests/run.py brains_dem     (KHÔNG mạng)

Bối cảnh 0.9.239: list_brains() dùng `p.rglob("*.md")` cho TỪNG brain - đi hết cây, không
trần, không offload. Đo được 136ms mỗi request trên 4 brain / 837 file, tăng tuyến tính theo
vault, mà dashboard gọi nó lúc BOOT. Đúng lỗi này đã được chẩn cho /viec/all và ghi hẳn
comment tiếng Việt trong main.py, nhưng /brains thì để nguyên suốt từ đó.

Test quan trọng nhất ở đây là "event loop vẫn thở": đó là thứ đã làm VPS trả 404 toàn trang
(request nặng bỏ đói healthcheck -> Docker gắn unhealthy -> Traefik gỡ route).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-braindem-")
os.environ.setdefault("JAVIS_STATE_DIR", _STATE)
_BRAINS = tempfile.mkdtemp(prefix="javis-braindem-brains-")
os.environ["BRAINS_DIR"] = _BRAINS       # main.py:432 đọc đúng tên này, KHÔNG có tiền tố JAVIS_

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


BASE = Path(main.BRAINS_DIR)

# CHỐT CHẶN - đừng gỡ. Test này TẠO brain giả, nên nếu BRAINS_DIR không phải thư mục tạm thì
# nó sẽ đẻ rác vào kho brain THẬT của người dùng. Đã xảy ra một lần: đặt nhầm tên biến môi
# trường (JAVIS_BRAINS_DIR thay vì BRAINS_DIR) làm 3019 file rác rơi vào brains/ thật.
# Chết ngay còn hơn ghi nhầm chỗ.
if BASE.resolve() != Path(_BRAINS).resolve():
    print(f"FAIL BRAINS_DIR không trỏ vào thư mục tạm: {BASE}\n"
          f"     (mong đợi {_BRAINS}). DỪNG để khỏi ghi rác vào brain thật.")
    sys.exit(1)

BASE.mkdir(parents=True, exist_ok=True)


def dung_brain(ten, n_note, n_an=0, sau=0):
    d = BASE / ten
    (d / "notes").mkdir(parents=True, exist_ok=True)
    for i in range(n_note):
        (d / "notes" / f"note-{i}.md").write_text(f"# ghi chú {i}\n", encoding="utf-8")
    for i in range(n_an):
        # .claude/skills = bản mirror do CHÍNH Javis sinh ra, không phải note của user
        p = d / ".claude" / "skills" / f"sk-{i}"
        p.mkdir(parents=True, exist_ok=True)
        (p / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    if sau:
        p = d
        for k in range(sau):
            p = p / f"tang{k}"
        p.mkdir(parents=True, exist_ok=True)
        (p / "that-sau.md").write_text("sâu\n", encoding="utf-8")
    return d


dung_brain("Brain A", 12, n_an=5)
dung_brain("Brain B", 3, sau=12)
(BASE / ".an-di").mkdir(exist_ok=True)          # thư mục ẩn ở mức brain -> phải bỏ qua


def goi():
    return asyncio.run(main.list_brains())


def forget_counts():
    """Empty the note-count memory of /brains (section 6), so a section that swaps the counter sees it run."""
    kept_counts = getattr(main, "_brain_note_counts", None)
    if kept_counts is not None:
        kept_counts.clear()


r = goi()
ten = {b["name"]: b for b in r["brains"]}
# "Brain Default" do _default_brain_dir() tự tạo (hành vi đúng: brain khởi đầu luôn có mặt).
check(f"liệt kê 2 brain vừa dựng + Brain Default tự sinh, bỏ qua thư mục ẩn ({sorted(ten)})",
      sorted(ten) == ["Brain A", "Brain B", "Brain Default"])
check("thư mục ẩn '.an-di' KHÔNG lọt vào danh sách brain", ".an-di" not in ten)
check("đúng một brain được đánh dấu mặc định",
      sum(1 for b in r["brains"] if b["is_default"]) == 1)

# ---- 1. Không đếm .md trong thư mục hệ thống (.claude/skills là mirror Javis tự sinh) ----
check(f"Brain A đếm 12 note, KHÔNG cộng 5 file trong .claude (được {ten['Brain A']['notes']})",
      ten["Brain A"]["notes"] == 12)
tat_ca = len(list((BASE / "Brain A").rglob("*.md")))
check(f"đối chiếu: rglob đếm tất cả là {tat_ca}, tức đã loại đúng 5 file hệ thống",
      tat_ca == 17)

# ---- 2. Trần độ sâu: file quá sâu không tính, nhưng cũng không làm hỏng lần đếm ----
check(f"Brain B đếm 3 note, file ở tầng 12 nằm ngoài trần độ sâu (được {ten['Brain B']['notes']})",
      ten["Brain B"]["notes"] == 3)

# ---- 3. Trần số lượng + cờ notes_capped ----
that = main._BRAINS_MD_CAP
try:
    main._BRAINS_MD_CAP = 5
    r2 = goi()
    a = [b for b in r2["brains"] if b["name"] == "Brain A"][0]
    b = [b for b in r2["brains"] if b["name"] == "Brain B"][0]
    check(f"chạm trần thì dừng đúng ở trần (được {a['notes']}, trần 5)", a["notes"] == 5)
    check("chạm trần thì gắn cờ notes_capped=True", a["notes_capped"] is True)
    check("chưa chạm trần thì notes_capped=False", b["notes_capped"] is False)
finally:
    main._BRAINS_MD_CAP = that

# ---- 4. Event loop vẫn thở trong lúc quét (đây là thứ đã gây 404 toàn trang trên VPS) ----
# Ép việc đếm CHẬM bằng cách vá _count_md thay vì đẻ hàng nghìn file thật. Lý do:
#   - Bản đầu tạo 3000 file để làm việc đủ nặng, tốn 27 giây chỉ để dựng dữ liệu.
#   - Mà 800 file thì CẢ HAI đường đều nhanh (15 và 16ms), nên phép đo không chứng minh
#     được gì - nó xanh vì việc quá nhẹ, không phải vì code đúng.
# Đĩa chậm mới là tình huống thật cần chống: vault lớn, ổ mạng, VPS I/O nghẽn.
_count_that = main._count_md
DO_TRE_GIA = 0.15


def _count_cham(root, cap):
    time.sleep(DO_TRE_GIA)      # giả lập ổ đĩa chậm / vault lớn
    return _count_that(root, cap)


async def do_do_tre(chay):
    """Bắn nhịp 5ms vào event loop rồi đo độ trễ LỚN NHẤT trong lúc `chay` chạy.

    Đo độ trễ chứ không đo thời gian hàm: hàm chạy 100ms trong thread là vô hại, còn hàm
    chạy 100ms trên loop là 100ms mọi request khác bị treo, kể cả healthcheck của Docker.
    """
    tre = []

    async def nhip():
        while True:
            t = time.perf_counter()
            await asyncio.sleep(0.005)
            tre.append((time.perf_counter() - t) * 1000)

    t_nhip = asyncio.create_task(nhip())
    await asyncio.sleep(0.05)          # cho nhịp chạy ổn định
    await chay()
    # BẮT BUỘC nhường loop trước khi huỷ nhịp. Hàm đồng bộ không có điểm await nào, nên
    # `await chay()` chạy thẳng inline: nhịp tim bị chặn suốt thời gian đó và chỉ ghi được
    # con số trễ SAU khi loop chạy lại. Huỷ ngay ở đây là mất đúng phép đo cần đo - và đó
    # là lý do bản trước báo 16ms cho cả hai đường, tức phép đo hoàn toàn vô nghĩa.
    await asyncio.sleep(0.02)
    t_nhip.cancel()
    try:
        await t_nhip
    except asyncio.CancelledError:
        pass
    return max(tre) if tre else 0.0


async def _duong_that():
    return await main.list_brains()


async def _duong_dong_bo():
    # Cố tình gọi bản đồng bộ THẲNG trên loop - đây là hành vi TRƯỚC 0.9.239.
    return main._list_brains_sync()


try:
    main._count_md = _count_cham
    forget_counts()             # the slow counter must really run
    tre_async = asyncio.run(do_do_tre(_duong_that))
    forget_counts()
    tre_sync = asyncio.run(do_do_tre(_duong_dong_bo))
finally:
    main._count_md = _count_that

nguong = DO_TRE_GIA * 1000
print(f"     (mỗi brain đếm mất {nguong:.0f} ms | độ trễ nhịp tim: qua to_thread "
      f"{tre_async:.0f} ms, gọi thẳng trên loop {tre_sync:.0f} ms)")

# Đối chứng: không có bước này thì test trên có thể xanh vì việc quá nhẹ chứ không phải
# vì code đúng. Bản đồng bộ PHẢI làm loop trễ ít nhất bằng một lần đếm.
check(f"phép đo có răng: gọi thẳng trên loop khoá loop >= {nguong:.0f} ms ({tre_sync:.0f} ms)",
      tre_sync >= nguong)
check(f"đường thật KHÔNG khoá loop dù mỗi brain đếm mất {nguong:.0f} ms ({tre_async:.0f} ms)",
      tre_async < nguong / 2)

# ---- 5. Một brain hỏng không giết cả danh sách ----
that_count = main._count_md


def _count_no(root, cap):
    if "Brain A" in str(root):
        raise OSError("giả lập ổ đĩa lỗi")
    return that_count(root, cap)


try:
    main._count_md = _count_no
    forget_counts()
    r3 = goi()
    ten3 = {b["name"]: b for b in r3["brains"]}
    check("một brain lỗi khi đếm vẫn được liệt kê (notes=0)",
          "Brain A" in ten3 and ten3["Brain A"]["notes"] == 0)
    check("các brain khác vẫn đếm bình thường", ten3["Brain B"]["notes"] == 3)
finally:
    main._count_md = that_count

# ---- 6. The count is remembered: a second read does not walk the disk again (speed review 2026-11-23) ----
# Measured on a real machine: /brains took 302 ms (p95 519 ms) because every call counted every brain again, and the
# dashboard calls it twice while it opens. Counted by calls, not by the clock, so a busy CI machine cannot flip it.
calls = []


def _count_spy(root, cap):
    calls.append(str(root))
    return that_count(root, cap)


def notes_of(result, name):
    return next(b for b in result["brains"] if b["name"] == name)["notes"]


try:
    main._count_md = _count_spy
    forget_counts()
    first = goi()
    n_first = len(calls)
    check(f"a first read counts every brain once ({n_first} counts for {len(first['brains'])} brains)",
          n_first == len(first["brains"]))
    second = goi()
    check(f"a second read within the fresh window counts nothing ({len(calls) - n_first} more counts)",
          len(calls) == n_first)
    check("and returns the same numbers", [b["notes"] for b in second["brains"]] == [b["notes"] for b in first["brains"]])

    # A new brain is counted at once, without recounting the others.
    dung_brain("Brain C", 4)
    before = len(calls)
    third = goi()
    check("a brain that just appeared is listed with its real count", notes_of(third, "Brain C") == 4)
    check(f"and only that one was counted ({len(calls) - before} counts)", len(calls) - before == 1)

    # A note written into a known brain shows once the fresh window has passed, never later.
    (BASE / "Brain C" / "notes" / "extra.md").write_text("# new\n", encoding="utf-8")
    check("inside the window the kept number is served", notes_of(goi(), "Brain C") == 4)
    ttl = getattr(main, "_BRAIN_NOTE_COUNT_TTL_S", None)
    check(f"the window is at most one minute ({ttl})", isinstance(ttl, (int, float)) and 0 < ttl <= 60)
    real_monotonic = time.monotonic
    try:
        main.time.monotonic = lambda: real_monotonic() + float(ttl or 0) + 1
        check("after the window the brain is counted again and shows the new note", notes_of(goi(), "Brain C") == 5)
    finally:
        main.time.monotonic = real_monotonic

    # A count that failed is not remembered: the next read tries again instead of showing 0 for a minute.
    def _count_fail_once(root, cap):
        raise OSError("disk hiccup")

    forget_counts()
    main._count_md = _count_fail_once
    check("a failed count lists the brain with 0", notes_of(goi(), "Brain A") == 0)
    main._count_md = _count_spy
    check("and the next read counts it for real", notes_of(goi(), "Brain A") == 12)

    # Memory stays one number per brain that exists: a deleted brain leaves nothing behind.
    import shutil
    shutil.rmtree(BASE / "Brain C")
    goi()
    kept_paths = {k[0] for k in getattr(main, "_brain_note_counts", {})}
    check("a deleted brain is dropped from the count memory", str(BASE / "Brain C") not in kept_paths)
finally:
    main._count_md = that_count

print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
