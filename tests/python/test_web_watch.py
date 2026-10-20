"""Theo dõi trang web không tốn token (0.239.0, server/web_watch.py).

Ý tưởng từ OpenMuse (page-diff.ts): mỗi lượt canh chỉ tải trang và so chữ, không gọi model. Các test
dưới đây giữ những chi tiết làm nó dùng được thật: thời gian tương đối không báo, đổi giá có báo, đọc
giá kiểu Việt Nam, giãn lần thử khi lỗi, tự dừng sau 5 lỗi, chống báo trùng, chặn mạng nội bộ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

import web_watch as ww


# ---------------------------------------------------------------- giá


@pytest.mark.parametrize("text, want", [
    ("Giá 1.250.000đ", [(1250000.0, "vnd")]),
    ("chỉ 1,25 triệu", [(1250000.0, "vnd")]),
    ("1tr2 thôi", [(1200000.0, "vnd")]),
    ("Giảm còn 250k", [(250000.0, "vnd")]),
    ("Giá: 990.000 ₫", [(990000.0, "vnd")]),
    ("2.000.000 VND", [(2000000.0, "vnd")]),
    ("4.500.000 đồng", [(4500000.0, "vnd")]),
    ("$12.99", [(12.99, "usd")]),
    ("1,299.00 USD", [(1299.0, "usd")]),
])
def test_doc_gia_kieu_viet_nam_va_usd(text, want):
    assert ww.parse_prices(text) == want


def test_nguong_va_gia_thap_nhat():
    assert ww.parse_threshold("1,5 triệu") == (1500000.0, "vnd")
    assert ww.parse_threshold("$20") == (20.0, "usd")
    assert ww.parse_threshold("1.000.000") == (1000000.0, None)
    assert ww.parse_threshold("rẻ thôi") is None
    trang = "Áo 1.250.000đ, quần 990.000đ, mũ $5"
    assert ww.cheapest_below(trang, ww.parse_threshold("1 triệu")) == (990000.0, "vnd")
    assert ww.cheapest_below(trang, ww.parse_threshold("$10")) == (5.0, "usd")   # khác tiền thì không so lẫn
    assert ww.cheapest_below(trang, ww.parse_threshold("900k")) is None
    assert ww.fmt_price(990000.0, "vnd") == "990.000đ"


# ---------------------------------------------------------------- so trang


def test_thoi_gian_tuong_doi_khong_tinh_la_doi():
    assert ww.without_relative_times("Đăng 3 phút trước, hôm qua, posted 2 hours ago, vừa xong") \
        == "Đăng <t>, <t>, posted <t>, <t>"
    d = ww.diff_page(["Bình luận 3 phút trước", "Áo đỏ"], ["Bình luận 10 phút trước", "Áo đỏ"])
    assert ww.count_diff(d) == 0


def test_doi_so_la_cap_nhat_con_lai_la_moi_va_da_xoa():
    d = ww.diff_page(["Giá áo: 1.250.000đ", "Sản phẩm A", "Sản phẩm B"],
                     ["Giá áo: 990.000đ", "Sản phẩm A", "Sản phẩm C"])
    assert d == {"added": ["Sản phẩm C"], "updated": ["Giá áo: 990.000đ"], "removed": ["Sản phẩm B"]}
    mo_ta = ww.describe_diff(d)
    assert "Sản phẩm C" in mo_ta and "990.000đ" in mo_ta and "Sản phẩm B" in mo_ta


def test_html_thanh_chu_bo_script_style():
    title, text = ww.html_to_text("<html><head><title>Shop</title><script>gia=1</script></head><body>"
                                  "<div>Giá <span>1.250.000</span>đ</div><style>x{}</style><p>Còn hàng</p></body></html>")
    assert title == "Shop"
    assert ww.page_lines(text) == ["Giá 1.250.000đ", "Còn hàng"]


def _w(**kw):
    base = {"id": "w_1", "title": "Áo đối thủ", "url": "https://shop.example/ao", "cond": "change", "value": "",
            "interval_min": 60, "last_hash": "", "timeless_hash": "", "lines_json": "[]", "matched": 0,
            "alert_seq": 0, "checks": 0, "failures": 0, "fail_streak": 0}
    base.update(kw)
    return base


def _ap(w, cols):
    w = dict(w)
    w.update(cols)
    return w


def test_canh_trang_doi_lan_dau_lam_moc_sau_do_chi_bao_khi_that_doi():
    w = _w()
    cols, alert = ww.observe(w, "Shop", "Áo đỏ\nGiá 1.250.000đ\nĐăng 3 phút trước")
    assert alert is None and cols["checks"] == 1                  # lượt đầu: chỉ ghi mốc
    w = _ap(w, cols)
    cols, alert = ww.observe(w, "Shop", "Áo đỏ\nGiá 1.250.000đ\nĐăng 9 phút trước")
    assert alert is None                                          # chỉ thời gian tương đối nhảy
    w = _ap(w, cols)
    cols, alert = ww.observe(w, "Shop", "Áo đỏ\nGiá 990.000đ\nĐăng 12 phút trước")
    assert alert and "990.000đ" in alert["body"] and alert["key"].startswith("watch:w_1:1:")
    w = _ap(w, cols)
    cols, alert2 = ww.observe(w, "Shop", "Áo đỏ\nGiá 890.000đ\nĐăng 15 phút trước")
    assert alert2 and alert2["key"] != alert["key"]               # mỗi lần đổi một khoá riêng


def test_canh_cum_chu_bao_mot_lan_khi_xuat_hien():
    w = _w(cond="contains", value="Còn hàng")
    cols, alert = ww.observe(w, "", "Tạm hết hàng")
    assert alert is None
    w = _ap(w, cols)
    cols, alert = ww.observe(w, "", "Áo đỏ: CÒN HÀNG, giao trong ngày")
    assert alert and "Còn hàng" in alert["title"]
    w = _ap(w, cols)
    cols, alert = ww.observe(w, "", "Áo đỏ: còn hàng, giao trong ngày")
    assert alert is None                                          # vẫn còn đó: không báo lại
    w = _ap(w, ww.observe(w, "", "Tạm hết hàng")[0])
    assert ww.observe(w, "", "Còn hàng rồi")[1]                   # hết rồi có lại: báo lại


def test_canh_gia_duoi_nguong():
    w = _w(cond="price_below", value="1 triệu")
    cols, alert = ww.observe(w, "", "Giá 1.250.000đ")
    assert alert is None
    cols, alert = ww.observe(_ap(w, cols), "", "Giá sốc 950.000đ")
    assert alert and "950.000đ" in alert["title"] and "1.000.000đ" in alert["title"]


def test_loi_gian_dan_roi_tu_dung_va_bao_mot_lan():
    w = _w()
    gap = []
    for _ in range(4):
        cols, alert = ww.after_failure(w, "Trang trả lỗi 503")
        assert alert is None
        gap.append(round((cols["next_at"] - cols["last_at"]) / 60))
        w = _ap(w, cols)
    assert gap == [2, 4, 8, 16]
    cols, alert = ww.after_failure(w, "Trang trả lỗi 503")
    assert cols["status"] == "paused" and alert and alert.get("failed") and "503" in alert["body"]
    key1 = alert["key"]
    # Mở lại, chạy được một lúc, rồi hỏng tiếp: lần dừng sau vẫn được báo (khoá mới).
    w = _ap(w, dict(cols, status="active", failures=0))
    w = _ap(w, ww.observe(w, "", "ok")[0])
    for _ in range(5):
        cols, alert = ww.after_failure(w, "timeout")
        w = _ap(w, cols)
    assert alert and alert["key"] != key1


# ---------------------------------------------------------------- an toàn địa chỉ


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://localhost:7777/hub/mcp", "http://10.0.0.5/",
                                 "http://169.254.169.254/latest/meta-data/", "ftp://example.com/",
                                 "https://example.com:8443/", "file:///etc/passwd"])
def test_chan_mang_noi_bo_va_dia_chi_la(url):
    with pytest.raises(ww.FetchError):
        ww.check_url(url)


# ---------------------------------------------------------------- tính năng


def _feature(tmp_path, monkeypatch):
    monkeypatch.setattr(ww, "check_url", lambda url: "shop.example")
    sent = []

    async def send(chat, text, **kw):
        sent.append({"chat": chat, "text": text, **kw})
        return True, ""

    f = ww.WebWatchFeature(ww.WebWatchDeps(state_dir=lambda: tmp_path, brain_root=lambda b: str(b), send=send,
                                          channels=lambda: (False, "bot Telegram chưa bật")))
    return f, sent


def test_tao_kiem_tham_so_va_chong_trung(tmp_path, monkeypatch):
    f, _ = _feature(tmp_path, monkeypatch)
    assert f.create("/b", "https://shop.example/ao", "contains", "")[1]           # thiếu cụm chữ
    assert f.create("/b", "https://shop.example/ao", "price_below", "rẻ")[1]      # ngưỡng không đọc được
    assert f.create("/b", "https://shop.example/ao", "gi-do")[1]
    w, err = f.create("/b", "https://shop.example/ao", interval_min=1)
    assert not err and w["interval_min"] == ww.MIN_INTERVAL and w["title"] == "shop.example"
    assert "w_" in f.create("/b", "https://shop.example/ao")[1]                   # cùng trang, cùng điều kiện
    assert not f.create("/khac", "https://shop.example/ao")[1]                    # brain khác: được
    f.store.close()


def test_canh_that_gui_bao_dung_nguoi_co_khoa_chong_trung(tmp_path, monkeypatch):
    f, sent = _feature(tmp_path, monkeypatch)
    pages = iter(["Giá 1.250.000đ", "Giá 990.000đ"])

    async def fetch(url):
        return url, "Shop", next(pages)

    monkeypatch.setattr(ww, "fetch", fetch)
    w, _ = f.create("/b", "https://shop.example/ao", owner_chat="web:s1", title="Áo")
    assert asyncio.run(f.tick()) == 1 and not sent                                # lượt đầu: mốc
    f.store.update(w["id"], next_at=0)
    asyncio.run(f.tick())
    assert len(sent) == 1
    s = sent[0]
    assert s["chat"] == "web:s1" and s["brain"] == "/b" and s["dedup"].startswith(f"watch:{w['id']}:1:")
    assert s["viec"]["kind"] == "watch" and "990.000đ" in s["text"]
    assert f.store.get(w["id"])["checks"] == 2
    f.store.close()


def test_tom_tat_ai_chi_khi_bat(tmp_path, monkeypatch):
    f, sent = _feature(tmp_path, monkeypatch)
    hoi = []

    async def summarize(prompt):
        hoi.append(prompt)
        return "Đối thủ giảm giá 21%."

    f.deps.summarize = summarize
    pages = {"a": iter(["Giá 1.250.000đ", "Giá 990.000đ"]), "b": iter(["Giá 1.250.000đ", "Giá 990.000đ"])}

    async def fetch(url):
        return url, "", next(pages[url[-1]])

    monkeypatch.setattr(ww, "fetch", fetch)
    a, _ = f.create("/b", "https://shop.example/a", summarize=False)
    b, _ = f.create("/b", "https://shop.example/b", summarize=True)
    for _ in range(2):
        asyncio.run(f.check(a["id"]))
        asyncio.run(f.check(b["id"]))
    assert len(hoi) == 1 and "DỮ LIỆU" in hoi[0]                                  # đúng một lần, chỉ mục đã bật
    assert any("Đối thủ giảm giá 21%" in x["text"] for x in sent)
    f.store.close()


def test_loi_5_lan_thi_dung_va_bao_mot_lan(tmp_path, monkeypatch):
    f, sent = _feature(tmp_path, monkeypatch)

    async def fetch(url):
        raise ww.FetchError("Trang trả lỗi 503")

    monkeypatch.setattr(ww, "fetch", fetch)
    w, _ = f.create("/b", "https://shop.example/ao")
    for _ in range(7):
        asyncio.run(f.check(w["id"]))
    w = f.store.get(w["id"])
    assert w["status"] == "paused" and "503" in w["last_error"]
    assert len(sent) == 1 and sent[0]["viec"]["status"] == "blocked"
    assert asyncio.run(f.tick()) == 0                                             # tạm dừng: không canh nữa
    f.control(w["id"], "resume")
    assert f.store.get(w["id"])["status"] == "active" and f.store.get(w["id"])["failures"] == 0
    assert f.control(w["id"], "delete")[0]["deleted"] and f.store.get(w["id"]) is None
    f.store.close()


# ---------------------------------------------------------------- tool javis_watch


def _plugin():
    spec = importlib.util.spec_from_file_location(
        "javis_watch_plugin_t", ROOT / "system" / "plugins" / "javis-watch" / "plugin.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_tool_javis_watch(tmp_path, monkeypatch):
    f, _ = _feature(tmp_path, monkeypatch)
    monkeypatch.setattr(ww, "_CURRENT", f)
    m = _plugin()

    class Ctx:
        vault_root = str(tmp_path / "brain")

    out = asyncio.run(m._chay({"op": "create", "url": "https://shop.example/ao", "condition": "price_below",
                               "value": "1 triệu", "chat_id": "web:s1"}, Ctx()))
    assert out.startswith("Đã tạo mục theo dõi") and "không tốn token" in out
    assert "chưa có kênh ngoài" in out                                            # nói thẳng: không tới điện thoại
    wid = out.split("Đã tạo mục theo dõi: ")[1].split(" ")[0]
    assert wid in asyncio.run(m._chay({"op": "list"}, Ctx()))
    assert "Đã tạm dừng" in asyncio.run(m._chay({"op": "pause", "id": wid}, Ctx()))

    class Khac:
        vault_root = str(tmp_path / "brain-khac")

    assert asyncio.run(m._chay({"op": "delete", "id": wid}, Khac())).startswith("ERROR")   # brain khác: không đụng
    assert "Đã xoá" in asyncio.run(m._chay({"op": "delete", "id": wid}, Ctx()))
    assert asyncio.run(m._chay({"op": "create", "url": "https://shop.example/ao", "condition": "contains"},
                               Ctx())).startswith("ERROR")
    f.store.close()


def test_khach_cua_bot_khong_thay_tool():
    import mcp_hub
    assert "javis_watch" in mcp_hub.OWNER_ONLY_TOOLS


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
