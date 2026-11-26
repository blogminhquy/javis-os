"""Connector NotebookLM. Chạy tay / CI:

    python tests/run.py notebooklm_connector

Không cần pytest, không chạm mạng.

Vì sao có file này. Sổ tay ghi việc này là "viết MCP server wrapper cho notebooklm-py", nhưng
thư viện đó đã đóng gói sẵn một MCP server (console script `notebooklm-mcp`, transport stdio),
nên phần Javis làm chỉ là MỘT mục trong kho connector. Cái gì chỉ là dữ liệu thì rất dễ gõ
sai mà không ai thấy, nên ba thứ sau phải có test canh:

  1. LỆNH CHẠY. Tên package (notebooklm-py) khác tên lệnh (notebooklm-mcp) nên bắt buộc
     `--from`, và phải kèm extra [mcp] vì fastmcp không nằm trong dependency lõi - thiếu nó
     thì lệnh vẫn chạy nhưng chết ngay ở import, và người dùng chỉ thấy "kết nối lỗi".
     Đúng loại bẫy đã dính ở connector google-keep.
  2. PHÂN LOẠI QUYỀN. Tool CHIA SẺ notebook ra ngoài phải nằm nhóm nguy hiểm. Thư viện tự
     đánh dấu chúng là "không phá huỷ" (đúng theo nghĩa dữ liệu), nhưng với người dùng thì
     chia sẻ nhầm là đã lộ - gỡ lại được cũng không rút lại được việc người ta đã đọc.
  3. KHÔNG XẾP VÀO NHÓM GOOGLE. Nhóm đó là các connector đi chung MỘT key OAuth client;
     NotebookLM mượn cookie phiên trình duyệt, cách đăng nhập và rủi ro khác hẳn.
  4. KHÔNG CÓ Ô HỒ SƠ (NOTEBOOKLM_PROFILE). Thư viện hễ thấy biến đó là BỎ QUA
     NOTEBOOKLM_AUTH_JSON: đi tìm file storage_state.json của hồ sơ trong HOME cô lập
     (trống trơn vì isolate_home) rồi chết FileNotFoundError, user chỉ thấy "process
     đóng stdout". Tái hiện cả hai chiều 14/08/2026. Đa tài khoản đã phân biệt sẵn
     bằng isolate_home (mỗi kết nối một HOME riêng theo slug) nên ô này vừa thừa
     vừa là bẫy.
  5. PHIÊN NẰM TRONG FILE THƯ VIỆN TỰ CẬP NHẬT (issue #1859, 26/11/2026). Đưa phiên qua biến môi
     trường thì cookie Google xoay vòng không bao giờ được lưu, kết nối chết sau vài giờ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import sys

import mcp_catalog as mc

loi = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        loi.append(ten)


con = mc.get("notebooklm")
check("catalog có connector notebooklm", bool(con))
if not con:
    print("\nFAIL - test_notebooklm_connector: thiếu hẳn connector")
    sys.exit(1)

# ---- 1. Lệnh chạy ----
args = con.get("args") or []
check("chạy qua uvx", con.get("command") == "uvx")
check("transport stdio", con.get("transport") == "stdio")
check("CANARY: có --from (tên package khác tên lệnh)", "--from" in args, args)
check("CANARY: kèm extra [mcp] (thiếu là chết ở import fastmcp)",
      "notebooklm-py[mcp]@latest" in args, args)
check("gọi đúng console script notebooklm-mcp", "notebooklm-mcp" in args, args)
check("khai là cần uv", bool((con.get("requires") or {}).get("uv")))
# Phiên nằm trong ~/.notebooklm của HOME; không cô lập thì hai tài khoản đè nhau, và xoá
# kết nối rồi đấu lại vẫn xài đúng phiên cũ (đúng lỗi đã gặp ở connector Google).
check("mỗi kết nối một HOME riêng", con.get("isolate_home") is True)

# ---- 2. Đăng nhập ----
fields = {f["key"]: f for f in ((con.get("auth") or {}).get("fields") or [])}
check("có ô dán phiên đăng nhập", "auth_json" in fields)
check("ô đó map sang đúng biến môi trường thư viện đọc",
      fields.get("auth_json", {}).get("env") == "NOTEBOOKLM_AUTH_JSON")
check("CANARY: không có ô hồ sơ (NOTEBOOKLM_PROFILE đè chết phiên dán, xem docstring mục 4)",
      "profile" not in fields)
check("CANARY: không field nào map sang NOTEBOOKLM_PROFILE",
      all(f.get("env") != "NOTEBOOKLM_PROFILE" for f in fields.values()))
# Kiểm qua chính build_env: kết nối CŨ còn secret 'profile' trong store cũng không được
# rò thành env - build_env chỉ map field còn khai trong catalog, test này canh đúng điều đó.
env = mc.build_env(con, {"auth_json": '{"cookies":[]}', "profile": "cong-viec"})
check("build_env phát NOTEBOOKLM_AUTH_JSON từ phiên dán",
      env.get("NOTEBOOKLM_AUTH_JSON") == '{"cookies":[]}')
check("CANARY: build_env không phát NOTEBOOKLM_PROFILE kể cả khi store còn secret cũ",
      "NOTEBOOKLM_PROFILE" not in env, env)
guide = (con.get("auth") or {}).get("guide", "")
check("hướng dẫn nêu rõ đây là cookie phiên, không phải OAuth", "cookie phiên" in guide.lower())
check("hướng dẫn có lệnh login thật để chạy", "notebooklm login" in guide)
check("hướng dẫn không còn bảo đặt tên hồ sơ", "tên hồ sơ" not in guide.lower())

# ---- 3. Phân loại quyền ----
tm = con.get("tool_meta") or {}
read, write, danger = set(tm.get("read") or []), set(tm.get("write") or []), set(tm.get("danger") or [])
check("mặc định chỉ đọc", con.get("default_perm") == "readonly")
check("có phân loại đủ ba nhóm", bool(read and write and danger))
check("không tool nào bị xếp hai nhóm", not (read & write) and not (read & danger) and not (write & danger))
for t in ("notebook_delete", "source_delete", "studio_delete"):
    check(f"{t} nằm nhóm nguy hiểm", t in danger)
for t in ("share_set_access", "share_set_user", "share_remove_user"):
    check(f"CANARY: {t} (chia sẻ ra ngoài) nằm nhóm nguy hiểm", t in danger)
for t in ("notebook_list", "source_read"):
    check(f"{t} là tool đọc", t in read)
for t in ("chat_ask", "source_add", "note_save"):
    check(f"{t} là tool ghi", t in write)

# classify() là thứ hub thật sự hỏi lúc chặn, nên kiểm qua chính nó chứ không chỉ đọc bảng.
check("hub xếp notebook_list là đọc", mc.classify(con, "notebook_list") == "read")
check("hub xếp share_set_access là nguy hiểm", mc.classify(con, "share_set_access") == "danger")

# ---- 4. Không thuộc nhóm Google một cửa ----
check("CANARY: không xếp vào nhóm google (đăng nhập khác hẳn)", not con.get("group"))

# ---- 5. Nói rõ rủi ro + trạng thái ----
risk = con.get("risk", "")
check("có mô tả rủi ro", len(risk) > 100)
check("rủi ro nêu rõ không phải OAuth giới hạn phạm vi", "OAuth" in risk)
check("rủi ro nói rõ đây là thư viện không chính thức", "không chính thức" in risk.lower())
check("đánh dấu beta (chưa test được đăng nhập thật)", con.get("status") == "beta")
check("có tool để kiểm tra kết nối sau khi đấu",
      (con.get("validate") or {}).get("tool") == "notebook_list")
for chuoi in (con.get("description", ""), risk, guide):
    check("không dùng em dash", "—" not in chuoi, chuoi[:60])

# ---- 5. The session lives in a file the library keeps up to date (issue #1859) ----
# notebooklm-py reads NOTEBOOKLM_AUTH_JSON before any file and never writes back to it, so Google's rotated cookies were
# lost and the connection signed out a few hours after each start. The paste now goes to the library's own session file.
import os  # noqa: E402
import stat  # noqa: E402
import tempfile  # noqa: E402
import mcp_store  # noqa: E402

home = tempfile.mkdtemp(prefix="javis-nblm-home-")
paste = '{"cookies":[{"name":"SID","value":"a"}],"origins":[]}'
env = {"NOTEBOOKLM_AUTH_JSON": paste, "HOME": home}
check("the paste is handed over as a file", mcp_store.notebooklm_session_file(env, home) is True)
f = os.path.join(home, ".notebooklm", "profiles", "default", "storage_state.json")
check("written where the library reads its default profile", os.path.isfile(f) and open(f).read() == paste)
if os.name == "posix":
    check("the session file is readable by its owner only", stat.S_IMODE(os.stat(f).st_mode) == 0o600,
          oct(stat.S_IMODE(os.stat(f).st_mode)))
check("the env value is removed (the library would read it before the file)", "NOTEBOOKLM_AUTH_JSON" not in env, env)
check("CANARY: no NOTEBOOKLM_PROFILE is set (rule 4)", "NOTEBOOKLM_PROFILE" not in env, env)
first_tag = env.get("JAVIS_NOTEBOOKLM_PASTE")
check("a tag of the paste joins the spawn env", bool(first_tag) and len(first_tag) == 12, env)

rotated = '{"cookies":[{"name":"SID","value":"rotated-by-google"}],"origins":[]}'
open(f, "w").write(rotated)
env2 = {"NOTEBOOKLM_AUTH_JSON": paste, "HOME": home}
mcp_store.notebooklm_session_file(env2, home)
check("a restart with the same paste keeps the cookies the library rotated", open(f).read() == rotated)
check("the same paste keeps the same tag (the running server is not restarted)",
      env2.get("JAVIS_NOTEBOOKLM_PASTE") == first_tag)

new_paste = '{"cookies":[{"name":"SID","value":"new-login"}],"origins":[]}'
env3 = {"NOTEBOOKLM_AUTH_JSON": new_paste, "HOME": home}
mcp_store.notebooklm_session_file(env3, home)
check("a new paste replaces the file", open(f).read() == new_paste)
check("a new paste changes the tag, so the server restarts on it", env3.get("JAVIS_NOTEBOOKLM_PASTE") != first_tag)

env4 = {"HOME": home}
check("no paste: nothing happens", mcp_store.notebooklm_session_file(env4, home) is False and env4 == {"HOME": home})
blocked = os.path.join(tempfile.mkdtemp(prefix="javis-nblm-blocked-"), "a-file")
open(blocked, "w").write("x")
env5 = {"NOTEBOOKLM_AUTH_JSON": paste}
check("a folder that cannot be made leaves the env value as before",
      mcp_store.notebooklm_session_file(env5, blocked) is False and env5.get("NOTEBOOKLM_AUTH_JSON") == paste)
src = open(os.path.join(SERVER, "mcp_store.py"), encoding="utf-8").read()
check("the spawn spec of an isolated NotebookLM connection goes through the file",
      '"notebooklm-mcp" in (str(lenh or "")' in src and "notebooklm_session_file(env, env.get(\"HOME\") or home)" in src)

if loi:
    print("\nFAIL - test_notebooklm_connector: " + str(len(loi)) + " lỗi: " + ", ".join(loi))
    sys.exit(1)
print("\nOK - test_notebooklm_connector: tất cả pass")
