"""Lời mời tặng sao GitHub (0.324.0): khi nào mời, mời bằng lời chào nào, số sao lấy từ đâu.

    python tests/run.py star_nudge

Không pytest, không mạng (gọi GitHub được thay bằng hàm giả). Những gì phải đúng, theo quyết
định của chủ repo ngày 25/10/2026:

1. Thả tim là lúc mời dễ nhất: lý do `heart` không cần đủ ngưỡng dùng.
2. Các lý do khác chỉ mời người đã dùng thật (7 ngày, 3 ngày dùng, 20 lượt chat), trừ cột mốc
   (tròn 50/100/... lượt, tròn 30/100/365 ngày) vì cột mốc tự nó là bằng chứng.
3. Không làm phiền: hiện rồi thì nghỉ ~1 ngày; X = 3 ngày; Để sau = 7 ngày; hoãn 6 lần là thôi;
   Đã tặng và Đừng hỏi nữa là thôi hẳn. Tự mở (manual) thì luôn được.
4. Số sao không viết cứng: đọc từ GitHub, nhớ 1 ngày (lỗi nhớ 1 giờ), mốc kế tiếp tự tính.
5. Route nhận đúng lý do và hành động, ghi trạng thái vào settings.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-star-")

import star_nudge as sn  # noqa: E402

fails = []


def check(ten, ok, them=None):
    print(("PASS: " if ok else "FAIL: ") + ten + ("" if ok or them is None else f"  [{them}]"))
    if not ok:
        fails.append(ten)


NOW = 2_000_000_000.0
NGAY = sn.NGAY
MOI = sn.trang_thai({})
DUNG_IT = {"turns": 2, "first_ts": NOW - 3600, "days": 1}
DUNG_DU = {"turns": 25, "first_ts": NOW - 9 * NGAY, "days": 4}

# ── 1. Mốc kế tiếp ──────────────────────────────────────────────────────────────────────────
for n, moc in ((0, 100), (286, 300), (300, 400), (999, 1000), (1240, 1500), (4999, 5000),
               (7300, 8000), (23000, 25000)):
    check(f"moc_tiep({n}) = {moc}", sn.moc_tiep(n) == moc, sn.moc_tiep(n))
check("goi_sao tính số còn thiếu", sn.goi_sao(286) == {"stars": 286, "milestone": 300, "remaining": 14})
check("không có số thì không có khối số", sn.goi_sao(None) is None)

# ── 2. Khi nào mời ──────────────────────────────────────────────────────────────────────────
check("thả tim: mời ngay cả người mới dùng", sn.chon_khoanh_khac(MOI, "heart", DUNG_IT, "1", NOW) == ("heart", 0))
check("việc xong: người mới dùng thì chưa mời", sn.chon_khoanh_khac(MOI, "work", DUNG_IT, "1", NOW) is None)
check("việc xong: dùng đủ lâu thì mời", sn.chon_khoanh_khac(MOI, "work", DUNG_DU, "1", NOW) == ("work", 0))
check("tự mở: luôn được, cả khi đã tặng",
      sn.chon_khoanh_khac(dict(MOI, state="done"), "manual", DUNG_IT, "1", NOW) == ("manual", 0))
check("lý do lạ: không mời", sn.chon_khoanh_khac(MOI, "spam", DUNG_DU, "1", NOW) is None)

# Mở app: cột mốc lượt chat, cột mốc ngày, bản mới
m100 = {"turns": 130, "first_ts": NOW - 2 * NGAY, "days": 2}
check("tròn 100 lượt: mời (không cần đủ 7 ngày)",
      sn.chon_khoanh_khac(MOI, "load", m100, "1", NOW) == ("milestone", 100))
check("cột mốc đã ăn mừng thì không lặp lại",
      sn.chon_khoanh_khac(dict(MOI, turns_seen=100, seen_version="1"), "load", m100, "1", NOW) is None)
k = {"turns": 30, "first_ts": NOW - 40 * NGAY, "days": 12}
check("tròn 1 tháng: mời", sn.chon_khoanh_khac(dict(MOI, turns_seen=0), "load",
                                                dict(k, turns=30), "1", NOW) == ("anniversary", 30))
check("bản mới (đã có phiên bản cũ ghi lại): mời",
      sn.chon_khoanh_khac(dict(MOI, seen_version="0.323.0", turns_seen=0, days_seen=30), "load",
                          dict(DUNG_DU, turns=40, first_ts=NOW - 35 * NGAY), "0.324.0", NOW) == ("update", 0))
check("lần đầu thấy app không phải 'vừa cập nhật'",
      sn.chon_khoanh_khac(dict(MOI, seen_version=""), "load", dict(DUNG_DU, turns=40), "0.324.0", NOW) is None)

# ── 3. Không làm phiền ──────────────────────────────────────────────────────────────────────
vua_hien = sn.danh_dau_da_hien(MOI, "heart", 0, "1", NOW)
check("vừa hiện thì nghỉ ~1 ngày", sn.chon_khoanh_khac(vua_hien, "heart", DUNG_DU, "1", NOW + 3600) is None)
check("qua ngày thì mời lại được", sn.chon_khoanh_khac(vua_hien, "heart", DUNG_DU, "1", NOW + NGAY) == ("heart", 0))
check("tự mở không tính là đã hiện", sn.danh_dau_da_hien(MOI, "manual", 0, "1", NOW)["shown_at"] == 0)
x = sn.ap_hanh_dong(MOI, "dismiss", NOW)
check("đóng X: hỏi lại sau 3 ngày", x["later_until"] == NOW + 3 * NGAY and x["state"] == "")
s = sn.ap_hanh_dong(MOI, "later", NOW)
check("Để sau: hỏi lại sau 7 ngày", s["later_until"] == NOW + 7 * NGAY)
check("đang hoãn thì cả tim cũng không mời", sn.chon_khoanh_khac(s, "heart", DUNG_DU, "1", NOW + NGAY) is None)
st = MOI
for i in range(sn.TOI_DA_HOAN):
    st = sn.ap_hanh_dong(st, "later" if i % 2 else "dismiss", NOW)
check(f"hoãn {sn.TOI_DA_HOAN} lần là thôi hẳn", st["state"] == "never")
check("Đã tặng: thôi hẳn", sn.chon_khoanh_khac(sn.ap_hanh_dong(MOI, "done", NOW), "heart", DUNG_DU, "1", NOW + 99 * NGAY) is None)
check("Đừng hỏi nữa: thôi hẳn", sn.chon_khoanh_khac(sn.ap_hanh_dong(MOI, "never", NOW), "load",
                                                    dict(DUNG_DU, turns=600), "1", NOW + 99 * NGAY) is None)
check("trạng thái hỏng đọc ra trung tính", sn.trang_thai({"state": "x", "later_until": "abc"})["state"] == ""
      and sn.trang_thai("rác")["later_until"] == 0.0)

# ── 4. Số sao: đọc GitHub, nhớ 1 ngày, lỗi nhớ 1 giờ ─────────────────────────────────────────
d = Path(tempfile.mkdtemp(prefix="javis-star-cache-"))
f = d / "github_stars.json"
goi = []


def hoi_ok():
    goi.append(1)
    return 286


def hoi_loi():
    goi.append(1)
    raise OSError("mất mạng")


check("lần đầu: hỏi GitHub", sn.so_sao(f, NOW, hoi_ok) == 286 and len(goi) == 1)
check("trong ngày: dùng số đã nhớ, không hỏi lại", sn.so_sao(f, NOW + 3600, hoi_ok) == 286 and len(goi) == 1)
check("qua ngày: hỏi lại", sn.so_sao(f, NOW + NGAY + 1, hoi_ok) == 286 and len(goi) == 2)
goi.clear()
f.unlink()
check("GitHub lỗi: không có số (không đoán)", sn.so_sao(f, NOW, hoi_loi) is None and len(goi) == 1)
check("lỗi được nhớ 1 giờ: không hỏi lại ngay", sn.so_sao(f, NOW + 600, hoi_loi) is None and len(goi) == 1)
check("sau 1 giờ: thử lại", sn.so_sao(f, NOW + 3601, hoi_ok) == 286 and len(goi) == 2)
f.write_text("rác", encoding="utf-8")
check("file nhớ hỏng: hỏi lại bình thường", sn.so_sao(f, NOW, hoi_ok) == 286)

# ── 5. Đếm mức dùng từ kho hội thoại ────────────────────────────────────────────────────────
sn._DUNG_CACHE.update(at=0.0, v=None)
cau = []


def read(sql, params=()):
    cau.append(sql)
    return [{"n": 42, "t0": NOW - 10 * NGAY, "d": 5}]


v = sn.dem_dung(read, NOW)
check("đếm lượt, lượt đầu, số ngày", v == {"turns": 42, "first_ts": NOW - 10 * NGAY, "days": 5}, v)
check("chỉ đếm tin người dùng gõ ở dashboard", "m.role = 'user'" in cau[0] and "'web'" in cau[0])
sn.dem_dung(read, NOW + 60)
check("nhớ 10 phút, không quét bảng mỗi lần", len(cau) == 1)
sn._DUNG_CACHE.update(at=0.0, v=None)
check("kho lỗi: coi như chưa dùng, không vỡ",
      sn.dem_dung(lambda *a: (_ for _ in ()).throw(RuntimeError("x")), NOW) == {"turns": 0, "first_ts": 0.0, "days": 0})

# ── 6. Route ─────────────────────────────────────────────────────────────────────────────────
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import routes.star_nudge as rsn  # noqa: E402

cfg = {}


def doc_cfg():
    return json.loads(json.dumps(cfg))


def ghi_cfg(patch):
    cfg.update(json.loads(json.dumps(patch)))
    return cfg


sdir = Path(tempfile.mkdtemp(prefix="javis-star-state-"))
# Số sao đã nhớ, ghi đúng lúc này: route không bao giờ gọi GitHub thật trong test (một mốc thời gian ở
# tương lai bị coi là hỏng và hỏi lại mạng, đã từng làm test này đọc 287 sao thật thay vì 286).
import time  # noqa: E402
(sdir / "github_stars.json").write_text(json.dumps({"n": 286, "at": time.time()}), encoding="utf-8")
sn._DUNG_CACHE.update(at=0.0, v=None)
app = FastAPI()
rsn.register(app, rsn.StarNudgeDeps(read_settings=doc_cfg, update_settings=ghi_cfg,
                                     read_sql=lambda sql, p=(): [{"n": 0, "t0": None, "d": 0}],
                                     state_dir=sdir, version=lambda: "0.324.0"))
c = TestClient(app)
r = c.post("/star-nudge/check", json={"reason": "heart"}).json()
check("route: thả tim thì mời, kèm số sao thật", r.get("show") is True and r.get("kind") == "heart"
      and r.get("count") == {"stars": 286, "milestone": 300, "remaining": 14}, r)
check("route: lần mời được ghi vào settings", cfg.get("star_nudge", {}).get("shown_at", 0) > 0)
check("route: mời liền lần nữa thì không", c.post("/star-nudge/check", json={"reason": "heart"}).json().get("show") is False)
check("route: lý do lạ bị từ chối", c.post("/star-nudge/check", json={"reason": "x"}).status_code == 400)
check("route: hành động lạ bị từ chối", c.post("/star-nudge/action", json={"action": "x"}).status_code == 400)
check("route: thân không phải JSON bị từ chối gọn", c.post("/star-nudge/action", content=b"abc").status_code == 400)
r = c.post("/star-nudge/action", json={"action": "done"}).json()
check("route: Đã tặng được ghi", r.get("state") == "done" and cfg["star_nudge"]["state"] == "done", r)
check("route: tự mở vẫn được sau khi đã tặng",
      c.post("/star-nudge/check", json={"reason": "manual"}).json().get("kind") == "manual")

# ── 7. Lời mời không hứa điều có thể đổi ────────────────────────────────────────────────────
vi = json.loads((ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8"))
en = json.loads((ROOT / "dashboard" / "i18n" / "en.json").read_text(encoding="utf-8"))
loi = " ".join(v for k, v in vi.items() if k.startswith("star.")).lower()
# Chủ repo 25/10: sau này có thể có bản trả phí và quảng cáo ở bản miễn phí; chỉ hứa "luôn có bản miễn phí".
check("không hứa 'không quảng cáo'", "quảng cáo" not in loi)
check("không hứa 'không thu phí'", "thu phí" not in loi and "không tốn" not in loi)
check("có câu 'luôn có một bản miễn phí'", "luôn có một bản miễn phí" in loi)
check("vi và en đủ cặp khoá star.*", {k for k in vi if k.startswith("star.")} == {k for k in en if k.startswith("star.")})
check("số sao không viết cứng trong lời mời (đọc từ GitHub qua {n}/{con}/{moc})",
      "286" not in loi and "{n}" in vi["star.count"] and "{moc}" in vi["star.count"])

if fails:
    raise SystemExit(f"{len(fails)} FAIL")
print("OK")
