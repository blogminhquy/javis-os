"""Thẻ kết nối Google Workspace phải nói ĐÚNG và ĐỦ để làm theo được một lèo.

    python tests/run.py google_workspace_setup

Không cần pytest, không chạm mạng.

Bối cảnh (báo từ người dùng thật, 2026-07-30): hướng dẫn trong modal "khó hiểu, bị sai".
Soát lại thì có ba chỗ hỏng thật, không phải chuyện chữ nghĩa:

1. Thiếu hẳn biến OAUTHLIB_INSECURE_TRANSPORT=1. workspace-mcp nhận Client ID + Secret nên
   chạy luồng OAuth confidential, mà chỗ nó hứng kết quả là http://localhost:8000/oauth2callback.
   oauthlib mặc định ném InsecureTransportError với http, nên bấm đồng ý xong quay về vẫn lỗi
   và hướng dẫn không có chữ nào cứu được. README upstream khai biến này 'required'.
2. Bảo bật đúng 4 API trong khi tier 'core' phục vụ cả Sheets, Slides, Forms, Tasks, Danh bạ -
   mô tả thẻ hứa những thứ đó nhưng làm theo hướng dẫn thì chúng chết lặng.
3. Cảnh báo "phải có màn hình" nằm ở BƯỚC CUỐI. Người cài trên VPS đọc tới đó là đã bỏ ra
   10 phút tạo project, bật API, tạo OAuth client - rồi mới biết đường này không đi được.

Test này khoá cả ba, vì cả ba đều là loại lỗi im lặng: không có test thì lần sửa sau chỉ cần
sơ ý là quay lại y nguyên mà CI vẫn xanh.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import json
import sys

import mcp_catalog

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


catalog = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))
ws = next(c for c in catalog["connectors"] if c["id"] == "google-workspace")
auth = ws.get("auth") or {}
steps = auth.get("steps") or []
guide = auth.get("guide") or ""
all_steps = " ".join(s.get("text", "") for s in steps)

# ---- 1. Biến môi trường sống còn cho luồng đăng nhập ----
check("khai env tĩnh OAUTHLIB_INSECURE_TRANSPORT=1 (thiếu là đăng nhập không bao giờ xong)",
      (ws.get("env") or {}).get("OAUTHLIB_INSECURE_TRANSPORT") == "1")
env = mcp_catalog.build_env(mcp_catalog.get("google-workspace"),
                            {"client_id": "abc.apps.googleusercontent.com",
                             "client_secret": "GOCSPX-x", "user_email": "a@b.com"})
check("build_env THẬT SỰ đẩy biến đó xuống tiến trình con",
      env.get("OAUTHLIB_INSECURE_TRANSPORT") == "1")
check("build_env vẫn đẩy đủ client id/secret/email như trước",
      env.get("GOOGLE_OAUTH_CLIENT_ID") and env.get("GOOGLE_OAUTH_CLIENT_SECRET")
      and env.get("USER_GOOGLE_EMAIL"))

# ---- 2. Cảnh báo "cần máy có màn hình" phải đến TRƯỚC khi bắt người ta làm việc ----
def _chi_so_buoc(tu_khoa):
    for i, s in enumerate(steps):
        if tu_khoa in s.get("text", "").lower():
            return i
    return -1


i_man_hinh = _chi_so_buoc("vps")
i_project = _chi_so_buoc("tạo một project")
check("có bước cảnh báo VPS / máy có màn hình", i_man_hinh >= 0)
check("cảnh báo đó đứng TRƯỚC bước tạo project (đọc xong mới biết có nên làm không)",
      0 <= i_man_hinh < i_project)
check("cảnh báo chỉ đường sang thẻ Lịch/Gmail dùng được trên VPS",
      "gmail" in steps[i_man_hinh].get("text", "").lower() if i_man_hinh >= 0 else False)

# ---- 3. Danh sách API phải phủ đúng những gì thẻ này hứa ----
for api in ("Gmail API", "Google Calendar API", "Google Drive API", "Google Docs API"):
    check(f"hướng dẫn nêu {api}", api in all_steps)
for api in ("Google Sheets API", "Google Slides API", "Google Forms API", "People API",
            "Google Tasks API"):
    check(f"hướng dẫn nêu cả {api} (tier core có nhóm tool này)", api in all_steps)
check("nói rõ quên bật API nào thì chỉ nhóm tool đó chết, không phải hỏng cả kết nối",
      "phần còn lại vẫn chạy" in all_steps)

# ---- 4. Chống lẫn với thẻ Lịch/Gmail: Desktop app KHÔNG có URI chuyển hướng ----
check("nói rõ client Desktop không phải khai URI chuyển hướng",
      "URI chuyển hướng" in all_steps and "KHÔNG" in all_steps)
check("chốt lại loại client là Desktop app", "Desktop app" in all_steps)

# ---- 5. Ô email: nhãn phải nói hậu quả của việc bỏ trống ----
f_email = next((f for f in (auth.get("fields") or []) if f.get("key") == "user_email"), {})
check("ô email còn là tuỳ chọn (không chặn người dùng)", f_email.get("optional") is True)
check("nhãn ô email nói rõ bỏ trống thì phiền, không chỉ ghi 'tuỳ chọn'",
      "nên điền" in (f_email.get("label") or ""))
check("có bước dặn điền email trước khi bấm Kết nối", "ô email" in all_steps)

# ---- 6. Cảnh báo 'ứng dụng chưa được xác minh' - chỗ người dùng hay đứng hình rồi bỏ cuộc ----
check("dặn cách qua màn 'ứng dụng chưa được xác minh'",
      "chưa được xác minh" in all_steps and "Nâng cao" in all_steps)
check("dặn tick hết ô quyền", "TICK HẾT" in all_steps)

# ---- 7. guide (bản dự phòng cho UI cũ) phải cùng nội dung, không lệch pha với steps ----
for tu in ("VPS", "Desktop app", "Google Sheets API", "TICK HẾT"):
    check(f"guide dự phòng cũng có '{tu}'", tu in guide)
check("CANARY: guide không còn câu cũ 'Bật Gmail API, Calendar API, Drive API, Docs API.'",
      "Bật Gmail API, Calendar API, Drive API, Docs API." not in guide)

# ---- 8. Quy tắc trình bày: step là MỘT <li> không giữ xuống dòng (CSS .conn-steps) ----
check("không step nào nhét ký tự xuống dòng (dashboard nuốt mất, thành một cục chữ)",
      not any("\n" in s.get("text", "") for s in steps))
check("không có em/en dash trong step", not any(("—" in s.get("text", "") or "–" in s.get("text", ""))
                                                for s in steps))

# ---- 9. MỌI connector chạy workspace-mcp đều phải có biến đó, không riêng google-workspace ----
# google-tasks dùng CHUNG server này (chỉ khác --tools tasks) nên dính y hệt. Vá một cái mà bỏ
# cái kia là để lại đúng nửa con bug, và nửa còn lại thì không ai nhớ.
chay_workspace_mcp = [c for c in catalog["connectors"]
                      if "workspace-mcp" in (c.get("args") or [])]
check("tìm được các connector chạy workspace-mcp", len(chay_workspace_mcp) >= 2)
thieu = [c["id"] for c in chay_workspace_mcp
         if (c.get("env") or {}).get("OAUTHLIB_INSECURE_TRANSPORT") != "1"]
check("mọi connector workspace-mcp đều khai OAUTHLIB_INSECURE_TRANSPORT: "
      + (", ".join(thieu) or "đạt"), not thieu)
# Cả hai thẻ đều mở trình duyệt trên máy chủ nên đều phải cảnh báo trước, không riêng thẻ gộp.
thieu_canh_bao = [c["id"] for c in chay_workspace_mcp
                  if "vps" not in " ".join(s.get("text", "") for s in
                                           ((c.get("auth") or {}).get("steps") or [])).lower()]
check("mọi connector workspace-mcp đều cảnh báo trước về VPS/màn hình: "
      + (", ".join(thieu_canh_bao) or "đạt"), not thieu_canh_bao)

if _fails:
    print(f"\nFAIL - test_google_workspace_setup: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_google_workspace_setup: tất cả pass")
