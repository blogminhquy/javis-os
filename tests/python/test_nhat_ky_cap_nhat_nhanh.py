"""Trang Nhật ký cập nhật phải NHẸ và có cache.

Bối cảnh (chủ repo báo 2026-09-21: "trang này load khá chậm, và có vẻ bị lỗi nữa"):
CHANGELOG.md đã phình lên 939 KB / 680 phiên bản. Bản cũ của `changelog_index`, MỖI lời gọi,
đọc cả file cục bộ rồi parse, TẢI thêm 939 KB nữa từ raw.githubusercontent.com, parse tiếp,
rồi trả về 923 KB JSON - không một lớp cache nào. Trang Cập nhật lại gọi nó HAI lần nối đuôi,
nên đo được trên máy cục bộ là ~2,2 giây và 1,8 MB chỉ để vẽ 20 dòng. Trên VPS đi xa GitHub
thì đủ lâu để người dùng tưởng trang hỏng, mà không có lỗi nào hiện ra cả.

Ba điều file này khoá lại:
  1. `/changelog` trả THEO TRANG (mặc định 20 bản), kèm `total` tính trên danh sách đầy đủ.
  2. Gọi lại trong TTL thì KHÔNG đụng mạng lần nữa; `refresh=1` mới ép tải lại.
  3. GitHub hỏng KHÔNG làm trang trắng: vẫn trả phần nhật ký của bản đang cài.

Chạy:
    python tests/run.py nhat_ky_cap_nhat_nhanh
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-changelog-test-")

import main  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# ── CHANGELOG giả: 50 bản, bản đang cài là 0.5.0 nên 0.5.1 là "chưa cài" ─────
def _md(so_ban, tu=1):
    khoi = []
    for i in range(so_ban, tu - 1, -1):
        khoi.append(f"## [0.{i // 10}.{i % 10}] - 2026-09-01\n### Sửa lỗi\n- việc số {i}\n")
    return "\n".join(khoi)


LOCAL_MD = _md(50)
REMOTE_MD = _md(51)          # GitHub có thêm một bản chưa cài
_dem = {"mang": 0}


class _Resp:
    status_code = 200
    text = REMOTE_MD


class _Client:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        _dem["mang"] += 1
        return _Resp()


class _HttpxGia:
    AsyncClient = _Client


# Chặn mọi đường ra ngoài: file này phải chạy được khi CI không có mạng.
sys.modules["httpx"] = _HttpxGia
main._read_version = lambda: "0.5.0"
main._CL_LOCAL.update({"sig": ("gia",), "releases": main._parse_changelog(LOCAL_MD)})
main._cl_local_releases = lambda: main._CL_LOCAL["releases"]


def reset():
    main._CL_REMOTE.update({"at": 0.0, "releases": [], "err": None})
    main._CL_MERGED.update({"key": None, "data": None})
    _dem["mang"] = 0


async def chay():
    reset()

    # ── 1. Trả theo trang ────────────────────────────────────────────────────
    d = await main.changelog_index(limit=20, offset=0)
    check("trang đầu chỉ trả 20 bản, không trả cả kho", len(d["releases"]) == 20)
    check("total vẫn là số bản ĐẦY ĐỦ", d["total"] == 51)
    check("bản mới nhất đứng đầu", d["releases"][0]["version"] == "0.5.1")
    check("latest tính trên danh sách đầy đủ", d["latest"] == "0.5.1")
    check("biết là có bản mới chưa cài", d["update_available"] is True)
    check("đánh dấu bản chưa cài", d["releases"][0]["installed"] is False)
    check("đánh dấu bản đang chạy", any(r.get("is_current") for r in d["releases"]))

    d2 = await main.changelog_index(limit=20, offset=20)
    check("trang hai lấy đúng đoạn tiếp theo",
          len(d2["releases"]) == 20 and d2["releases"][0]["version"] != d["releases"][0]["version"])
    check("trang hai vẫn báo đúng total", d2["total"] == 51)
    check("trang hai nhớ offset đã hỏi", d2["offset"] == 20)

    d3 = await main.changelog_index(limit=0)
    check("limit=0 vẫn lấy được tất cả", len(d3["releases"]) == 51)

    # ── 2. Cache: gọi lại thì không đụng mạng ────────────────────────────────
    check("lần đầu có ra mạng đúng một lần", _dem["mang"] == 1)
    for _ in range(5):
        await main.changelog_index(limit=20)
    check("gọi thêm 5 lần nữa KHÔNG ra mạng lần nào", _dem["mang"] == 1)

    await main.changelog_index(limit=20, refresh=True)
    check("refresh=True mới ép tải lại", _dem["mang"] == 2)

    # ── 3. Payload phải nhỏ ──────────────────────────────────────────────────
    d = await main.changelog_index(limit=20)
    kich_thuoc = len(json.dumps(d, ensure_ascii=False).encode("utf-8"))
    day_du = len(json.dumps(await main.changelog_index(limit=0), ensure_ascii=False).encode("utf-8"))
    check(f"một trang nhẹ hơn hẳn cả kho ({kich_thuoc} < {day_du})", kich_thuoc * 2 < day_du)


asyncio.run(chay())


# ── 4. GitHub hỏng thì trang vẫn có nội dung ─────────────────────────────────
class _ClientHong(_Client):
    async def get(self, url):
        _dem["mang"] += 1
        raise OSError("mạng hỏng")


async def chay_mat_mang():
    reset()
    _HttpxGia.AsyncClient = _ClientHong
    try:
        d = await main.changelog_index(limit=20)
        check("mất mạng vẫn trả nhật ký của bản đang cài", len(d["releases"]) == 20)
        check("mất mạng thì nêu lỗi ra chứ không giấu", bool(d["error"]))
        check("mất mạng thì không bịa ra bản mới", d["update_available"] is False)
    finally:
        _HttpxGia.AsyncClient = _Client


asyncio.run(chay_mat_mang())

print("")
print(("ĐỎ: " + ", ".join(fails)) if fails else "OK - test_nhat_ky_cap_nhat_nhanh: tất cả pass")
sys.exit(1 if fails else 0)
