"""Model `chatgpt-web` đã GỠ HẲN ở 0.64.20, và người đang dùng nó không bị bỏ rơi.

    python tests/run.py go_chatgpt_web

Vì sao gỡ: model này lái một trình duyệt vào chatgpt.com, mà Javis chạy trên máy chủ thuê nên
Cloudflare chặn theo IP. Chủ repo đưa hai dự án làm cùng việc để đối chiếu
(`miuuyy/codex-chatgpt-web`, `XiaoDuoYa/codex-with-chatgpt`): CẢ HAI đều chạy trình duyệt
trên máy của người dùng, không dự án nào có đường qua Cloudflare từ máy chủ. Chủ repo chốt gỡ
ngày 23/09.

Gỡ một model có ba cái bẫy, và file này khoá cả ba:

  1. **Người đang chọn nó.** Cài đặt của họ vẫn ghi `chatgpt-web`, danh mục model đã lưu cũng
     còn nó. Nếu `_codex_safe_model` coi nó là hợp lệ thì Codex nhận `-m chatgpt-web` và mọi
     lượt chat hỏng. Nhánh Codex có sẵn cơ chế TỰ CHỮA (đổi sang model thật, ghi lại cài đặt,
     báo một dòng) - chỉ cần hàm đó trả về một model KHÁC.
  2. **Rác trên đĩa.** Nút "Thư viện lái trình duyệt" từng cài chừng 140 MB vào thư mục state.
     Gỡ nút mà không dọn thì ai từng bấm cài mang rác mãi, không còn nút nào để gỡ.
  3. **Mảnh sót.** Một route, một import, một khối giao diện còn trỏ vào thứ đã xoá là lỗi chờ
     ngày nổ.
"""
from _paths import ROOT, SERVER, moi_route  # noqa: E402,F401
import importlib.util
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-gocgw-")

import config as cfg  # noqa: E402
import main  # noqa: E402
import optional_tools as ot  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + ((f"  [{them}]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1) Người đang chọn chatgpt-web phải rơi về một model Codex THẬT
# ============================================================

def _dat_catalog(ds):
    s = cfg.read_settings()
    s.setdefault("model", {}).setdefault("catalog", {})["openai-oauth"] = ds
    cfg.write_settings(s)


# Cảnh xấu nhất và cũng là cảnh thật: danh mục đã lưu từ bản cũ VẪN còn `chatgpt-web` (bản cũ
# nối nó vào cuối danh sách của Codex rồi lưu lại).
_dat_catalog(["gpt-5.5", "gpt-5-codex", "chatgpt-web"])
check("chọn chatgpt-web -> đổi sang model Codex thật",
      main._codex_safe_model("chatgpt-web") == "gpt-5.5", main._codex_safe_model("chatgpt-web"))
check("kể cả viết hoa/thừa khoảng trắng thì cũng không lọt",
      main._codex_safe_model("  chatgpt-web ") != "chatgpt-web")
check("model Codex bình thường vẫn giữ nguyên", main._codex_safe_model("gpt-5-codex") == "gpt-5-codex")

# CANARY: danh mục chỉ còn đúng chatgpt-web (máy không có Codex CLI). Bản cũ lấy `cat[0]` thì
# đưa ngược chatgpt-web cho Codex; phải ra rỗng để Codex tự chọn model mặc định của nó.
_dat_catalog(["chatgpt-web"])
check("CANARY: danh mục chỉ còn model đã gỡ -> trả rỗng, không trả lại chính nó",
      main._codex_safe_model("chatgpt-web") == "", main._codex_safe_model("chatgpt-web"))

_dat_catalog([])
check("danh mục rỗng -> trả rỗng", main._codex_safe_model("chatgpt-web") == "")

check("có hằng số liệt kê model đã gỡ, kèm lý do", "chatgpt-web" in main._MODEL_DA_GO)

# Nhánh Codex của dashboard VÀ Telegram phải tự chữa khi model khác đi, không chỉ một bên.
_src_main = (SERVER / "main.py").read_text(encoding="utf-8")
check("nhánh Codex vẫn tự chữa model đã lưu (dashboard + Telegram)",
      _src_main.count('_set_main_model(_fix, "openai-oauth", actual_model)') >= 2)


# ============================================================
# 2) Dọn rác thư viện playwright đã cài
# ============================================================

(ot.PYLIBS_DIR / "playwright" / "driver").mkdir(parents=True, exist_ok=True)
(ot.PYLIBS_DIR / "playwright" / "driver" / "node").write_text("x", encoding="utf-8")
check("có thư mục cũ -> dọn và báo là có dọn", ot.don_thu_vien_cu() is True)
check("thư mục cũ đã biến mất", not ot.PYLIBS_DIR.exists())
check("chạy lần nữa không có gì -> không ném, báo không dọn", ot.don_thu_vien_cu() is False)

_src_tools = (SERVER / "routes" / "tools.py").read_text(encoding="utf-8")
check("dọn chạy lúc khởi động, ở thread riêng (không bắt server chờ)",
      "optional_tools.don_thu_vien_cu" in _src_tools and "threading.Thread" in _src_tools)

check("trang Công cụ chỉ còn trình duyệt", [d["id"] for d in ot.danh_sach()] == ["browser"])
check("mục thư viện không cài được nữa", ot.bat_dau_cai("pylib-playwright").get("ok") is False)
check("trình duyệt quay về bản nhẹ --only-shell (đủ cho Playwright MCP)",
      "--only-shell" in ot._lenh_cai("browser")[0])


# ============================================================
# 3) Không còn mảnh sót
# ============================================================

for _ten in ("web_transport", "web_engine", "web_state", "web_tool_protocol"):
    check(f"module {_ten} đã xoá", not (SERVER / f"{_ten}.py").exists()
          and importlib.util.find_spec(_ten) is None)

# `moi_route` đi ĐỆ QUY qua router con. Đọc thẳng `main.app.routes` là chỉ thấy tầng ngoài
# (fastapi 0.141 bọc mỗi include_router), và phép thử "route này phải MẤT" sẽ xanh oan.
_duong = {getattr(r, "path", "") for r in moi_route(main.app)}
check("không còn route /web-chat nào", not any(p.startswith("/web-chat") for p in _duong),
      sorted(p for p in _duong if p.startswith("/web-chat")))
for _chu in ("la_model_web", "MODEL_WEB", "_web_bat", "_dung_web_engine",
             "_model_codex_thay_the", "web_transport", "web_engine", "web_state"):
    check(f"main.py không còn nhắc {_chu}", _chu not in _src_main)

_con = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("dashboard không còn khối ChatGPT Web", "veThreChatGPTWeb" not in _con
      and "/web-chat" not in _con and "webChatBox" not in _con)

_docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
check("ảnh Docker không còn cài xvfb (chỉ ChatGPT Web cần)", "xvfb" not in _docker)

for _doc in ("docs/16-cau-hinh-env.md", "docs/en/16-env-configuration.md"):
    check(f"{_doc} không còn biến JAVIS_ENABLE_WEB_CHAT",
          "JAVIS_ENABLE_WEB_CHAT" not in (ROOT / _doc).read_text(encoding="utf-8"))
check("tài liệu hướng dẫn cũ đã xoá", not (ROOT / "docs" / "29-chatgpt-web.md").exists())
check("spec cũ còn lại làm hồ sơ, có ghi rõ ĐÃ GỠ",
      "ĐÃ GỠ ở 0.64.20" in (ROOT / "docs/dev/2026-09-chatgpt-web-model-spec.md").read_text(encoding="utf-8"))

# main.py có một regex CỐ Ý khớp ký tự gạch dài trong nội dung người dùng; đó là mã nhận diện,
# không phải chữ viết ra, nên bỏ đúng chuỗi đó trước khi soi.
_REGEX_NHAN_DIEN = "[-\u2013\u2014]"
for _f in ("tests/python/test_go_chatgpt_web.py", "server/optional_tools.py", "server/main.py",
           "server/routes/tools.py", "server/sessions.py"):
    _t = (ROOT / _f).read_text(encoding="utf-8").replace(_REGEX_NHAN_DIEN, "")
    check(f"{_f} không dùng gạch dài (luật CLAUDE.md)", "\u2014" not in _t and "\u2013" not in _t)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_go_chatgpt_web: tất cả pass")
