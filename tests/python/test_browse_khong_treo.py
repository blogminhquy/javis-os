"""Endpoint /browse không được làm nghẽn event loop.

SỰ CỐ THẬT 2026-07-28: bản VPS trả 404 cả trang. Container `javis` vẫn "Up" nhưng Docker
gắn nhãn unhealthy nên Traefik gỡ route. Log cho thấy healthcheck 200 đều mỗi 30 giây rồi
CÂM HẲN ngay sau dòng `GET /browse?path=/home` - app không chết, app TREO.

Nguyên nhân: `browse` khai `async def` nhưng bên trong quét đĩa đồng bộ. Đoạn
`glob.glob(f"{full}/**/*.md", recursive=True)[:500]` trông như có trần 500 nhưng lát cắt
chỉ áp lên KẾT QUẢ - glob đã đi hết cây thư mục trước đó rồi. Trên VPS, /home ôm cả brains
lẫn dữ liệu dự án khác nên một request duyệt thư mục khoá cứng event loop, healthcheck
không được phục vụ, và cả server biến mất khỏi Traefik.

Hai điều kiện phải giữ: đếm có TRẦN THẬT (dừng giữa chừng), và quét chạy ngoài event loop.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import inspect
import time

import main


def _cay_sau(root, nhanh: int, moi_nhanh: int):
    """Dựng cây đủ lớn để cách quét cũ phải đi hết mới trả lời được."""
    for i in range(nhanh):
        d = root / f"nhanh{i}"
        for j in range(6):          # lồng sâu
            d = d / f"muc{j}"
        d.mkdir(parents=True)
        for k in range(moi_nhanh):
            (d / f"note{k}.md").write_text("x", encoding="utf-8")


def test_dem_md_co_tran_that_dung_giua_chung(tmp_path):
    """Chạm trần là DỪNG, không đi nốt phần còn lại của cây."""
    _cay_sau(tmp_path, nhanh=4, moi_nhanh=200)      # 800 file .md
    n = main._count_md(str(tmp_path), cap=50)
    assert n == 50, f"phải dừng đúng ở trần, nhận {n}"


def test_dem_md_dung_khi_duoi_tran(tmp_path):
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "con").mkdir()
    (tmp_path / "con" / "b.md").write_text("x", encoding="utf-8")
    (tmp_path / "con" / "bo-qua.txt").write_text("x", encoding="utf-8")
    assert main._count_md(str(tmp_path), cap=500) == 2


def test_dem_md_khong_di_theo_symlink_vong(tmp_path):
    """Symlink trỏ ngược lên cha làm glob recursive lặp vô tận. Phải bỏ qua symlink."""
    con = tmp_path / "con"
    con.mkdir()
    (con / "a.md").write_text("x", encoding="utf-8")
    try:
        (con / "vong").symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        return          # Windows không có quyền tạo symlink thì bỏ qua ca này
    xong = time.time()
    n = main._count_md(str(tmp_path), cap=500)
    assert n == 1
    assert time.time() - xong < 5, "đi theo symlink vòng nên treo"


def test_dem_md_bo_qua_thu_muc_khong_doc_duoc(tmp_path):
    """Thư mục cấm quyền không được làm hỏng cả lần đếm."""
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    assert main._count_md(str(tmp_path / "khong-ton-tai"), cap=500) == 0


def test_browse_khong_quet_dia_tren_event_loop(monkeypatch):
    """Chốt chặn của sự cố: phần chạm đĩa phải chạy NGOÀI event loop.

    Đo tất định bằng cách thay phần quét bằng một hàm chặn 0.3 giây rồi xem nhịp tim
    song song có còn đập không. Chặn thật trên event loop thì nhịp tim đứng hình - đúng
    như healthcheck 30 giây bị bỏ đói trên VPS. Không đo bằng cây thư mục thật vì bản đã
    sửa quét xong quá nhanh, phép đo sẽ hoá may rủi."""
    def cham_nhung_khong_duoc_khoa(path):
        time.sleep(0.3)
        return {"path": path, "parent": None, "dirs": []}

    monkeypatch.setattr(main, "_browse_sync", cham_nhung_khong_duoc_khoa)

    async def scenario():
        nhip = 0

        async def tim():
            nonlocal nhip
            while True:
                nhip += 1
                await asyncio.sleep(0.01)

        h = asyncio.create_task(tim())
        await asyncio.sleep(0.02)
        truoc = nhip
        await main.browse(path="/bat-ky")
        sau = nhip
        h.cancel()
        return sau - truoc

    # Bị khoá thật thì nhịp đếm được là 0. Đòi hơn 2 nhịp đã tách bạch hoàn toàn hai
    # trường hợp; đòi hơn 5 chỉ thêm điều kiện về TỐC ĐỘ máy (nhịp 0.01s trên máy chạy CI
    # đang tải nặng trôi thành vài chục ms), tức một chỗ đỏ oan không đổi lại được gì.
    assert asyncio.run(scenario()) > 2, "event loop bị khoá suốt lúc quét thư mục"


def test_browse_cay_khong_lo_van_tra_nhanh(tmp_path):
    """Trần đếm phải là trần THẬT: cây to cỡ nào cũng trả lời trong tích tắc.
    Bản cũ (glob rồi mới cắt) phải đi hết cây nên thời gian tăng theo số file."""
    _cay_sau(tmp_path, nhanh=6, moi_nhanh=400)      # 2400 file .md
    bat_dau = time.time()
    res = asyncio.run(main.browse(path=str(tmp_path)))
    mat = time.time() - bat_dau
    assert len(res["dirs"]) == 6
    assert all(d["md"] <= main._BROWSE_MD_CAP for d in res["dirs"])
    # 2400 file: bản có trần trả lời trong tích tắc, bản cũ (glob hết cây rồi mới cắt) đi
    # hết cây nên chậm hẳn một bậc. 8s vẫn tách bạch hai bản mà không phụ thuộc đĩa nhanh chậm.
    assert mat < 8, f"quét mất {mat:.1f}s - trần không có tác dụng"


def test_browse_van_tra_dung_du_lieu(tmp_path):
    (tmp_path / "brain-a").mkdir()
    (tmp_path / "brain-a" / "note.md").write_text("x", encoding="utf-8")
    (tmp_path / ".an").mkdir()
    res = asyncio.run(main.browse(path=str(tmp_path)))
    ten = [d["name"] for d in res["dirs"]]
    assert ten == ["brain-a"], "thư mục ẩn phải bị lọc"
    assert res["dirs"][0]["md"] == 1
    assert res["path"] == str(tmp_path)


def test_browse_bao_loi_gon_khi_path_sai():
    res = asyncio.run(main.browse(path="/duong-dan-khong-ton-tai-abc"))
    assert "error" in res and res["dirs"] == []


def test_browse_van_la_async():
    assert inspect.iscoroutinefunction(main.browse)


if __name__ == "__main__":
    # CI chạy TỪNG FILE như script (`python tests/python/test_x.py`), không gọi pytest.
    # Thiếu block này thì file chỉ định nghĩa hàm rồi thoát 0 - test "xanh" mà chưa từng
    # chạy một assertion nào. Bảy file từng ở tình trạng đó, và bốn assertion trong số
    # chúng đang ĐỎ mà không ai biết (xem CHANGELOG 0.13.2).
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
