"""usage_index.summary() nhớ đệm theo vân tay chỉ số (0.421.0).

    python tests/run.py usage_summary_nho     (KHÔNG mạng)

Bối cảnh: mở trang Mức dùng là ba lượt cùng tính summary(this_month): /usage/summary,
/usage/insights (gọi summary bên trong) và /usage/tong-quan, ba luồng song song giành nhau
một nhân Python. Đo 30/10/2026 trên 15 nghìn dòng: mỗi lượt 0,05 s khi chạy riêng, cả trang
0,7-1,7 s khi chạy chung. Nay summary() nhớ kết quả theo kỳ + vân tay file chỉ số.

Rủi ro của nhớ đệm là im lặng trả số CŨ, nên file này khoá đúng mấy điều:
  - gọi lại khi chỉ số không đổi: không tính lại, kết quả y hệt bản tính thẳng;
  - có dòng mới ghi vào chỉ số: tính lại ngay, không chờ hết hạn;
  - bên gọi sửa kết quả thì lần sau không bị dính;
  - nhiều luồng cùng hỏi một kỳ: chỉ tính một lần.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import os
import sys
import tempfile
import threading

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-usagenho-"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import usage_index as u      # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


HOM_NAY = u._today_local().isoformat()


def chen(n, path="/p/a"):
    w = u._connect()
    for i in range(n):
        w.execute("INSERT INTO file_daily(path,day,provider,source,activity,model,project,"
                  "input,output,cache_read,cache_create) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (f"{path}/{i}", HOM_NAY, "claude", "javis", "chat", "claude-opus-5", "prj", 100, 50, 0, 0))
    w.commit()
    w.close()


u.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
chen(5)

dem = {"n": 0}
_goc = u._summary_that


def _dem(*a, **k):
    dem["n"] += 1
    return _goc(*a, **k)


u._summary_that = _dem

# ---- 1. Gọi lại khi chỉ số không đổi ----
a = u.summary(period="this_month")
b = u.summary(period="this_month")
check(f"gọi hai lần, chỉ số không đổi: tính một lần (đếm {dem['n']})", dem["n"] == 1)
check("kết quả nhớ y hệt bản tính thẳng", b == _goc(period="this_month"))
check("có số thật (5 dòng x 150 token)", a["kpi"]["tokens"] == 750)

# ---- 2. Bên gọi sửa kết quả không làm hỏng bản nhớ ----
a["kpi"]["tokens"] = 0
a["timeseries"].clear()
c = u.summary(period="this_month")
check("sửa kết quả trả về không dính sang lần sau", c["kpi"]["tokens"] == 750 and len(c["timeseries"]) > 0)

# ---- 3. Có dòng mới: tính lại ngay ----
dem["n"] = 0
chen(3, "/p/b")
d = u.summary(period="this_month")
check(f"ghi thêm dòng vào chỉ số: tính lại (đếm {dem['n']})", dem["n"] == 1)
check(f"và ra số mới (đang là {d['kpi']['tokens']})", d["kpi"]["tokens"] == 8 * 150)

# ---- 4. Kỳ khác, nhánh khác là khoá khác ----
dem["n"] = 0
u.summary(period="last_month")
u.summary(period="this_month", provider="codex")
check(f"kỳ khác và nhánh khác tính riêng (đếm {dem['n']})", dem["n"] == 2)
check("nhánh codex không lẫn số claude", u.summary(period="this_month", provider="codex")["kpi"]["tokens"] == 0)

# ---- 5. Nhiều luồng cùng hỏi một kỳ: một lần tính ----
dem["n"] = 0
u._NHO_SUMMARY.clear()
kq = []
ts = [threading.Thread(target=lambda: kq.append(u.summary(period="this_week"))) for _ in range(6)]
for t in ts:
    t.start()
for t in ts:
    t.join()
check(f"6 luồng cùng lúc: tính một lần (đếm {dem['n']})", dem["n"] == 1)
check("cả 6 luồng nhận cùng một kết quả", len(kq) == 6 and all(x == kq[0] for x in kq))

# ---- 6. Hết hạn thì tính lại dù vân tay chưa đổi ----
dem["n"] = 0
song = u._NHO_SONG
u._NHO_SONG = 0.0
u.summary(period="this_month")
u._NHO_SONG = song
check(f"quá hạn sống: tính lại (đếm {dem['n']})", dem["n"] == 1)

# ---- 7. Kỳ sai vẫn báo lỗi như cũ (main.py bắt ValueError thành 400) ----
try:
    u.summary(period="month")
    check("kỳ sai báo ValueError", False)
except ValueError:
    check("kỳ sai báo ValueError", True)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
