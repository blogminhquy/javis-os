"""Công cụ TUỲ CHỌN: trình duyệt cài bằng nút bấm, không nhét sẵn vào ảnh (0.57.23).

    python tests/run.py cong_cu_tuy_chon

Chủ dự án 15/09: "về phần trình duyệt lên vps thì anh muốn có nút cài đặt ở trong phần plugin
để khiến đây là 1 lựa chọn, và khởi đầu khi cài đặt hermes agent cũng đưa ra các lựa chọn có
cài các tool hay không, anh nghĩ javis cũng nên như thế".

Ràng buộc không lách được, và nó quyết định cách chia:
  - Trong Docker, Javis chạy bằng user `javis` không phải root, mã nguồn để chỉ đọc. Nên phần
    cần `apt-get` (thư viện hệ thống cho Chromium) BẮT BUỘC nằm trong ảnh - Dockerfile lo, để
    riêng một lớp đo được. CI đo thật: 108 MB trên ảnh 1824 MB.
  - Bản thân trình duyệt thì KHÔNG vào ảnh: tải lúc chạy vào `STATE_DIR/browsers`, tức trên ổ
    gắn ngoài, nên sống qua mỗi lần cập nhật thay vì phải tải lại cả trăm MB.

Và một chốt dễ bỏ sót: máy cá nhân thường đã có sẵn Google Chrome, Playwright lái được luôn.
Mời họ tải thêm một bản Chromium nữa là mời một việc vô nghĩa, nên phải DÒ trước khi mời.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import re
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-congcu-"))

import optional_tools as ct  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


# ---- 1. Trạng thái đọc được, và không mời cài thừa ----
d = ct.trang_thai("browser")
check("trả về đủ thứ để vẽ một thẻ",
      all(k in d for k in ("id", "ten", "mo_ta", "trang_thai", "ly_do", "go_duoc", "dung_luong_uoc")))
check("trạng thái là một trong ba giá trị đã định",
      d["trang_thai"] in ("san_sang", "chua_cai", "dang_cai"), d["trang_thai"])
check("có lý do bằng LỜI cho người đọc, không phải mã máy", len(d["ly_do"]) > 15)
check("công cụ lạ thì báo lỗi rõ, không nổ", ct.trang_thai("khong-co-that").get("ok") is False)
check("danh sách trả về đúng số công cụ đang khai", len(ct.danh_sach()) == len(ct.CONG_CU))

# Máy nào có sẵn Chrome/Chromium thì PHẢI báo sẵn sàng, không mời tải.
he_thong = ct._chrome_he_thong()
if he_thong:
    check("máy đã có trình duyệt -> báo sẵn sàng, KHÔNG mời tải",
          d["trang_thai"] == "san_sang" and he_thong in d["ly_do"])
    check("không cho gỡ trình duyệt của HỆ THỐNG (Javis không đặt nó vào đó)", d["go_duoc"] is False)
else:
    check("máy chưa có gì -> mời cài", d["trang_thai"] == "chua_cai")

# ---- 2. Gỡ: chỉ đụng bản Javis tự tải ----
r = ct.go("browser")
check("chưa tải gì mà bấm gỡ thì từ chối kèm lý do",
      r["ok"] is False and "để gỡ" in r["error"])
check("gỡ công cụ lạ cũng từ chối gọn", ct.go("khong-co-that").get("ok") is False)

# ---- 3. Nơi tải phải nằm trên ổ GẮN NGOÀI, không phải cache tạm ----
check("tải vào STATE_DIR/browsers (sống qua mỗi lần cập nhật)",
      ct.BROWSERS_DIR.name == "browsers" and str(ct.BROWSERS_DIR).startswith(os.environ["JAVIS_STATE_DIR"]))
check("dùng đúng biến môi trường Playwright hiểu", ct.ENV_BROWSERS_PATH == "PLAYWRIGHT_BROWSERS_PATH")
check("có trần thời gian, không tải treo vô hạn", ct.TAI_TIMEOUT > 0)

# ---- 4. Trình duyệt mặc định phải ĐÚNG THEO MÁY ----
# Đặt sai chỗ này là connector đi tìm Google Chrome trên một container Debian rồi chết với câu
# lỗi không ai đoán ra.
md = ct.trinh_duyet_mac_dinh()
check("giá trị mặc định là chrome hoặc chromium", md in ("chrome", "chromium"), md)
if he_thong:
    check("máy có Chrome -> mặc định dùng chrome (khỏi tải gì)", md == "chrome")
else:
    check("máy không có gì -> mặc định chromium (bản Javis tải)", md == "chromium")
env = ct.env_playwright()
check("env luôn nói rõ dùng trình duyệt nào", env.get("PLAYWRIGHT_MCP_BROWSER") == md)
check("chưa tải thì KHÔNG đặt đường dẫn kho trình duyệt (để Playwright tự lo)",
      ct.ENV_BROWSERS_PATH not in env or ct._da_tai())

# ---- 5. Hub phải truyền env đó cho tiến trình Playwright ----
ms = open(os.path.join(ROOT, "server", "mcp_store.py"), encoding="utf-8").read()
check("mcp_store nhận biết connector Playwright theo LỆNH, không theo id",
      re.search(r'if "playwright" in \(str\(c\.get\("command"\)', ms) is not None)
check("và hỏi optional_tools chứ không tự biết tên biến của một connector",
      "optional_tools.env_playwright()" in ms)
check("dùng setdefault: người dùng tự chọn trong form thì KHÔNG bị đè",
      re.search(r"env_playwright\(\)\.items\(\):\s*\n\s*env\.setdefault", ms) is not None)

# ---- 6. Đường HTTP: đòi phiên thật, không nhận API token ----
rt = open(os.path.join(ROOT, "server", "routes", "tools.py"), encoding="utf-8").read()
check("cả ba endpoint đều kiểm phiên đăng nhập", rt.count("_DEPS.co_phien(request)") == 3)
check("cài chạy NỀN rồi trả về ngay (không giữ kết nối HTTP chờ tải cả trăm MB)",
      "bat_dau_cai" in rt and "trả về ngay" in rt)
mn = open(os.path.join(ROOT, "server", "main.py"), encoding="utf-8").read()
check("đăng ký bằng phiên cookie, giống trang Gói",
      re.search(r"tools_routes\.register\(app, tools_routes\.ToolsDeps\(\s*\n\s*co_phien=lambda r: cfgmod\.valid_session", mn) is not None)

# ---- 7. Task tải phải được GIỮ REF (bài học 0.57.18) ----
check("giữ ref mạnh cho task tải, không thả trôi cho bộ gom rác nuốt",
      "_TASKS.add(t)" in open(os.path.join(ROOT, "server", "optional_tools.py"), encoding="utf-8").read())

# ---- 8. Dockerfile: thư viện vào ảnh, TRÌNH DUYỆT thì không ----
df = open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8").read()
check("ảnh có thư viện hệ thống cho Chromium", "playwright@latest install-deps chromium" in df)
check("để RIÊNG một lớp và tắt được bằng build-arg",
      "ARG WITH_BROWSER_DEPS=1" in df and 'if [ "$WITH_BROWSER_DEPS" = "1" ]' in df)
check("CANARY: KHÔNG tải trình duyệt vào ảnh (đó là việc của nút bấm)",
      not re.search(r"playwright.*install\s+(--only-shell\s+)?chromium(?!\s*-deps)", df.replace("install-deps", "install_deps")))

# ---- 9. Giao diện: nút ở trang Công cụ, nhắc ở form Kết nối, hỏi ở trình hướng dẫn ----
cs = open(os.path.join(ROOT, "dashboard", "console.js"), encoding="utf-8").read()
check("trang Công cụ có khối công cụ tuỳ chọn", 'id="ctTuyChon"' in cs and "veCongCuTuyChon" in cs)
check("form đấu Playwright nhắc khi máy còn thiếu", "nhacCongCuThieu" in cs and 'id="ctNhac"' in cs)
check("nhắc cũng nhận biết theo LỆNH, khớp với phía server",
      'dau.indexOf("playwright")' in cs)
check("chỉ hỏi lại tiến độ khi ĐANG tải, không quay vòng vô ích",
      re.search(r"if \(dangCai\) _ctTimer = setTimeout", cs) is not None)

ap = open(os.path.join(ROOT, "dashboard", "app.js"), encoding="utf-8").read()
ix = open(os.path.join(ROOT, "dashboard", "index.html"), encoding="utf-8").read()
check("trình hướng dẫn có ô chọn cài trình duyệt", 'id="wzCtBrowser"' in ix and 'id="wzCongCu"' in ix)
check("khối đó MẶC ĐỊNH ẨN, chỉ hiện khi máy thật sự thiếu",
      'id="wzCongCu" style="display:none' in ix and 'ct.trang_thai === "chua_cai"' in ap)
check("tick rồi thì gọi cài ở nền, không chặn đường vào app",
      re.search(r'_ctB && _ctB\.checked[\s\S]{0,300}/tools/optional/install', ap) is not None)

# ---- 10. Chữ hiện cho người dùng phải có dấu, và không có em dash ----
import json  # noqa: E402
vi = json.load(open(os.path.join(ROOT, "dashboard", "i18n", "vi.json"), encoding="utf-8"))
en = json.load(open(os.path.join(ROOT, "dashboard", "i18n", "en.json"), encoding="utf-8"))
khoa = [k for k in vi if k.startswith(("cs.ct_", "wz.ct_"))]
check("có đủ chuỗi cho cả hai ngôn ngữ", len(khoa) >= 10 and all(k in en for k in khoa), len(khoa))
check("chuỗi tiếng Việt CÓ DẤU", any(re.search(r"[ạảãáàâăêôơưđ]", vi[k], re.I) for k in khoa))
check("không có em dash trong chuỗi mới",
      not any("\u2014" in vi[k] or "\u2014" in en[k] for k in khoa))

print(("\n%d FAIL" % len(_fails)) if _fails else "\nTat ca OK")
raise SystemExit(1 if _fails else 0)
