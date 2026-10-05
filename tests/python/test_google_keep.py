"""Test connector Google Keep trong system/mcp-catalog.json. Chạy tay / CI:

    python tests/run.py google_keep

Không cần pytest, không chạm mạng, không cần master token thật.
Phủ: entry tồn tại + đúng runner, map env của 3 ô đăng nhập, luật opt-in của UNSAFE_MODE
(mấu chốt giữ bản fork sạch), và lớp chặn cứng theo 3 mức quyền + trần của mode.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-keeptest-"))

import mcp_catalog  # noqa: E402

_fails = []

# 23 tool keep-mcp công bố ở README (feuerdev/keep-mcp).
OFFICIAL_TOOLS = [
    "find", "get_note",
    "create_note", "create_list", "update_note",
    "add_list_item", "update_list_item", "delete_list_item",
    "set_note_color", "pin_note", "archive_note", "trash_note", "restore_note", "delete_note",
    "list_labels", "create_label", "delete_label", "add_label_to_note", "remove_label_from_note",
    "list_note_collaborators", "add_note_collaborator", "remove_note_collaborator",
    "list_note_media",
]


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


con = mcp_catalog.get("google-keep")
check("catalog có connector 'google-keep'", con is not None)

if con is None:
    print(f"\nFAIL - test_google_keep: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)

# ---- hình dạng entry ----
check("transport = stdio", con.get("transport") == "stdio")
check("chạy bằng uvx (khớp các connector stdio sẵn có)", con.get("command") == "uvx")
# BẪY ĐÃ DẪM PHẢI, ĐỪNG "dọn gọn" thành `uvx keep-mcp`: package keep-mcp khai console script
# tên `mcp` (server.cli:main), TRÙNG tên với CLI của MCP SDK (mcp.cli:app) vốn là dependency
# của nó. Cài xong thì SDK thắng, nên `uvx --from keep-mcp mcp` chạy nhầm sang CLI của SDK.
# Đường duy nhất không mơ hồ là module `server/__main__.py`. Đã kiểm bằng bắt tay MCP thật.
check("args dùng --from + python -m server (KHÔNG phải `uvx keep-mcp`, xem ghi chú trên)",
      (con.get("args") or []) == ["--from", "keep-mcp@latest", "python", "-m", "server"])
check("default_perm = readonly (đấu xong chỉ đọc, tự nâng quyền sau)",
      con.get("default_perm") == "readonly")
check("có mô tả rủi ro master token", "MASTER TOKEN" in (con.get("risk") or "").upper())

# ---- 3 ô đăng nhập map đúng env ----
fields = {f["key"]: f for f in ((con.get("auth") or {}).get("fields") or [])}
check("ô email -> GOOGLE_EMAIL", (fields.get("google_email") or {}).get("env") == "GOOGLE_EMAIL")
check("ô token -> GOOGLE_MASTER_TOKEN",
      (fields.get("master_token") or {}).get("env") == "GOOGLE_MASTER_TOKEN")
check("ô unsafe -> UNSAFE_MODE", (fields.get("unsafe_mode") or {}).get("env") == "UNSAFE_MODE")
check("ô unsafe là TUỲ CHỌN (bỏ trống vẫn đấu được)",
      bool((fields.get("unsafe_mode") or {}).get("optional")))
check("email là BẮT BUỘC", not fields.get("google_email", {}).get("optional"))
# Từ 0.9.113 có ô App Password và Javis tự đổi ra token, nên master_token KHÔNG còn bắt buộc.
# Luật "phải có ÍT NHẤT MỘT trong hai" do cred_exchange kiểm phía server (xem test_cred_exchange),
# vì schema field hiện chỉ diễn đạt được bắt-buộc/tuỳ-chọn cho TỪNG ô, không diễn đạt được "một trong hai".
check("app_password và master_token đều TUỲ CHỌN (một trong hai là đủ)",
      bool(fields.get("app_password", {}).get("optional"))
      and bool(fields.get("master_token", {}).get("optional")))

# ---- luật opt-in của UNSAFE_MODE: mấu chốt giữ bản fork sạch ----
env_safe = mcp_catalog.build_env(con, {"google_email": "a@gmail.com", "master_token": "aas_et/x"})
check("bỏ trống ô unsafe -> env KHÔNG có UNSAFE_MODE (mặc định an toàn cho bản fork)",
      "UNSAFE_MODE" not in env_safe)
check("bỏ trống ô unsafe -> email và token vẫn được truyền",
      env_safe.get("GOOGLE_EMAIL") == "a@gmail.com"
      and env_safe.get("GOOGLE_MASTER_TOKEN") == "aas_et/x")

env_unsafe = mcp_catalog.build_env(con, {"google_email": "a@gmail.com",
                                         "master_token": "aas_et/x",
                                         "unsafe_mode": "true"})
check("gõ true vào ô unsafe -> env có UNSAFE_MODE=true",
      env_unsafe.get("UNSAFE_MODE") == "true")

# ---- tool_meta phủ đúng 23 tool, không thừa không thiếu ----
tm = con.get("tool_meta") or {}
declared = (tm.get("read") or []) + (tm.get("write") or []) + (tm.get("danger") or [])
check("không khai trùng tool", len(declared) == len(set(declared)))
check("phủ đủ 23 tool keep-mcp công bố",
      sorted(declared) == sorted(OFFICIAL_TOOLS))

# ---- lớp chặn cứng theo mức quyền ----
def allowed(perm, tool, mode="full"):
    ok, _ = mcp_catalog.allowed(con, perm, mode, tool)
    return ok


check("readonly: find CHO QUA", allowed("readonly", "find"))
check("readonly: get_note CHO QUA", allowed("readonly", "get_note"))
check("readonly: list_labels CHO QUA", allowed("readonly", "list_labels"))
check("readonly: create_note BỊ CHẶN", not allowed("readonly", "create_note"))
check("readonly: update_note BỊ CHẶN", not allowed("readonly", "update_note"))

check("safe: create_note CHO QUA", allowed("safe", "create_note"))
check("safe: update_note CHO QUA", allowed("safe", "update_note"))
check("safe: add_label_to_note CHO QUA", allowed("safe", "add_label_to_note"))
check("safe: delete_note BỊ CHẶN (xoá vĩnh viễn)", not allowed("safe", "delete_note"))
check("safe: delete_label BỊ CHẶN", not allowed("safe", "delete_label"))

# Bất đối xứng CÓ CHỦ Ý: mức Ghi nháp gỡ lại được note nhưng không tự vứt được.
check("safe: restore_note CHO QUA (luôn gỡ lại được)", allowed("safe", "restore_note"))
check("safe: trash_note BỊ CHẶN (không tự vứt được)", not allowed("safe", "trash_note"))

# Chia sẻ note ra người khác = rò dữ liệu ra ngoài, khác chất với sửa nội dung trong nhà.
check("safe: add_note_collaborator BỊ CHẶN (chia sẻ ra ngoài)",
      not allowed("safe", "add_note_collaborator"))
check("safe: remove_note_collaborator BỊ CHẶN",
      not allowed("safe", "remove_note_collaborator"))
check("full: add_note_collaborator CHO QUA", allowed("full", "add_note_collaborator"))
check("full: delete_note CHO QUA", allowed("full", "delete_note"))

# ---- trần của mode (loop nền) đè lên perm ----
check("mode suggest ép readonly: full + create_note vẫn BỊ CHẶN",
      not allowed("full", "create_note", mode="suggest"))
check("mode suggest: find vẫn CHO QUA", allowed("full", "find", mode="suggest"))
check("mode auto ép tối đa safe: full + create_note CHO QUA",
      allowed("full", "create_note", mode="auto"))
check("mode auto: full + delete_note vẫn BỊ CHẶN",
      not allowed("full", "delete_note", mode="auto"))

# ---- bản cho UI không lộ secret ----
pub = next((c for c in mcp_catalog.public_catalog() if c["id"] == "google-keep"), None)
check("public_catalog có google-keep", pub is not None)
check("public_catalog trả đủ 5 ô nhập (email, app password, oauth_token, master token, unsafe)",
      len((pub or {}).get("fields") or []) == 5)
check("public_catalog trả nút setup để UI vẽ 'Tạo App Password'",
      bool(((pub or {}).get("setup") or {}).get("links")))
check("public_catalog KHÔNG lộ tool_meta/validate nội bộ",
      "tool_meta" not in (pub or {}) and "validate" not in (pub or {}))

# ---- CANARY: chứng minh các check ở trên có quyền lực thật, không phải luôn-xanh ----
_fake = {"tool_meta": {"read": ["find"], "write": ["create_note"], "danger": ["delete_note"]}}
check("CANARY: connector giả cho phép create_note ở mức readonly thì check phải BẮT được "
      "-> tức mcp_catalog.allowed thật sự đang chặn chứ không trả True vô điều kiện",
      not mcp_catalog.allowed(_fake, "readonly", "full", "create_note")[0])

if _fails:
    print(f"\nFAIL - test_google_keep: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_google_keep: tất cả pass")
