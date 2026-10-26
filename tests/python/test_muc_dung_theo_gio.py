"""Trang Mức dùng, phần "24 giờ qua" (0.329.0): ba góc nhìn theo giờ phải đúng số.

    python tests/run.py muc_dung_theo_gio

Chủ repo 26/10 gửi ảnh một bảng theo dõi token tự dựng và bảo làm trang Mức dùng "hữu dụng hơn".
Ba thứ được lấy về, mỗi thứ một câu hỏi trang cũ không trả lời được:

1. `cua_so`: tổng cửa sổ 5 giờ tại MỖI giờ trong 24 giờ qua, để thấy đang lên hay xuống so với
   mốc (trần tự khai, không thì mức cao nhất từng chạm). Phải khớp đúng `cua_so()` ở giờ cuối.
2. `gio_24`: token từng giờ, tách theo provider, đủ 24 ô kể cả giờ không dùng.
3. `nhiet_7`: trung bình token mỗi ngày ở từng giờ trong ngày, chỉ tính 7 ngày TRỌN (hôm nay
   đang dở thì không kéo trung bình xuống), chia cho số ngày CÓ dùng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import re
import tempfile
from datetime import timedelta

_TMP = tempfile.mkdtemp(prefix="javis-tg-")
os.environ["JAVIS_STATE_DIR"] = _TMP
os.environ["JAVIS_CLAUDE_PROJECTS_DIR"] = os.path.join(_TMP, "claude-projects")
os.environ["JAVIS_CODEX_SESSIONS_DIR"] = os.path.join(_TMP, "codex-sessions")
os.makedirs(os.environ["JAVIS_CLAUDE_PROJECTS_DIR"], exist_ok=True)
os.makedirs(os.environ["JAVIS_CODEX_SESSIONS_DIR"], exist_ok=True)

import usage_index as ui  # noqa: E402
from datetime import datetime  # noqa: E402

fails = []


def check(ten, ok, them=None):
    print(("PASS: " if ok else "FAIL: ") + ten + ("" if ok or them is None else f"  [{them}]"))
    if not ok:
        fails.append(ten)


NOW = datetime(2026, 10, 26, 9, 30, tzinfo=ui._tz())


def seed(h, tokens, provider="claude", turns=1):
    c = ui._connect()
    try:
        c.execute("INSERT INTO file_hourly(path,hour,provider,tokens,turns) VALUES(?,?,?,?,?)",
                  ("p", h.strftime("%Y-%m-%dT%H"), provider, tokens, turns))
        c.commit()
    finally:
        c.close()


gio = lambda d, h: NOW.replace(day=d, hour=h, minute=0)  # noqa: E731
seed(gio(26, 9), 1000)                     # giờ hiện tại
seed(gio(26, 8), 2000, "codex")
seed(gio(26, 5), 4000)                     # giờ cuối còn trong cửa sổ 5 giờ (5,6,7,8,9)
seed(gio(26, 4), 8000)                     # ngoài cửa sổ của 9h, trong cửa sổ của 8h
seed(gio(25, 10), 16000, "api")            # 23 giờ trước: ô đầu tiên của 24 giờ
seed(gio(25, 9), 32000)                    # 24 giờ trước: ngoài gio_24
# 7 ngày trọn trước 26/10: ngày 19 tới 25. 3 ngày có dùng lúc 14h.
for d in (20, 22, 24):
    seed(gio(d, 14), 3000)
seed(gio(18, 14), 99999)                   # 8 ngày trước: ngoài nhiet_7

d = ui.theo_gio(5.0, now=NOW)
g24 = d["gio_24"]
check("đủ 24 ô giờ", len(g24) == 24, len(g24))
check("ô cuối là giờ hiện tại", g24[-1]["hour"] == "2026-10-26T09", g24[-1]["hour"])
check("ô đầu là 23 giờ trước", g24[0]["hour"] == "2026-10-25T10", g24[0]["hour"])
check("ô đầu đếm token api vào cột api", g24[0]["api"] == 16000 and g24[0]["total"] == 16000, g24[0])
check("tách provider: giờ 8 là codex", g24[-2]["codex"] == 2000 and g24[-2]["claude"] == 0, g24[-2])
check("giờ không dùng vẫn có ô, bằng 0", g24[-3]["total"] == 0)
check("token 24 giờ trước không lọt vào", sum(x["total"] for x in g24) == 1000 + 2000 + 4000 + 8000 + 16000)

cs = d["cua_so"]
check("cửa sổ 5 giờ có 24 điểm", len(cs) == 24)
check("điểm cuối = 9h + 8h + 5h (4h đã ra ngoài)", cs[-1]["tokens"] == 7000, cs[-1])
check("điểm 8h ôm cả 4h", cs[-2]["tokens"] == 2000 + 4000 + 8000, cs[-2])
check("CANARY: điểm cuối khớp đúng cua_so() hiện tại", cs[-1]["tokens"] == ui.cua_so(5.0, now=NOW)["tokens"])

nh = d["nhiet_7"]
# Ngày có dùng trong 7 ngày trọn: 20, 22, 24 (lúc 14h) và 25 (lúc 9h, 10h) = 4 ngày.
check("đếm 4 ngày có dùng trong 7 ngày trọn", nh["so_ngay"] == 4, nh["so_ngay"])
check("14h: 9000 chia 4 ngày có dùng", nh["tb_moi_gio"][14] == 2250, nh["tb_moi_gio"][14])
check("9h chỉ tính hôm qua, không tính hôm nay đang dở", nh["tb_moi_gio"][9] == 8000, nh["tb_moi_gio"][9])
check("giờ chỉ hôm nay có dùng thì bằng 0", nh["tb_moi_gio"][8] == 0 and nh["tb_moi_gio"][4] == 0)
check("ngày thứ 8 trở về trước không tính", max(nh["tb_moi_gio"]) < 99999)
check("24 giờ trong ngày", len(nh["tb_moi_gio"]) == 24)

trong = ui.theo_gio(5.0, now=datetime(2030, 1, 1, 0, 0, tzinfo=ui._tz()))
check("kho không có gì trong khoảng: không vỡ, nhiet_7 0 ngày", trong["nhiet_7"]["so_ngay"] == 0
      and all(x["total"] == 0 for x in trong["gio_24"]))

# Route: mốc so sánh là trần tự khai, không thì mức cao nhất từng chạm, và nói rõ là cái nào.
src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
m = re.search(r'@app\.get\("/usage/theo-gio"\)[\s\S]{0,1400}?return d\n', src)
check("route /usage/theo-gio có", bool(m))
than = m.group(0) if m else ""
check("mốc: trần khai trước, đỉnh sau, có cờ loại", "tran_5h" in than and "dinh_cua_so" in than
      and '"loai": "tran" if tran else "dinh"' in than)
check("route đăng ký sau star_nudge (bảng route chỉ dài thêm ở đuôi)",
      src.rfind('@app.get("/usage/theo-gio")') > src.rfind("star_nudge_routes.register"))

if fails:
    raise SystemExit(f"{len(fails)} FAIL")
print("OK")
